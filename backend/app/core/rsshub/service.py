"""RSS 订阅服务 - CRUD + 按分钟轮询去重 + 消息查询 + 增量通知队列"""
from datetime import datetime, timedelta, timezone
from collections import deque
from typing import Optional

from sqlalchemy import select, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rss import RssSource, RssItem
from app.core.settings import get_setting_int
from app.core.rsshub.parser import fetch_feed, clean_html, clean_text, clean_text
from app.utils.logger import logger
from app.utils import shanghai_now

_CN_TZ = timezone(timedelta(hours=8))
_MAX_ITEMS_PER_SOURCE = 500
_MAX_ITEMS_TOTAL = 20000
_MAX_RECENT = 300

# 增量通知队列：最近入库的消息，供前端全局通知轮询
_RECENT_ADDED: deque = deque(maxlen=_MAX_RECENT)


class RssService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 订阅源 CRUD ───────────────────────────────────────────

    async def list_sources(self) -> list[dict]:
        rows = (await self.db.execute(
            select(RssSource).order_by(RssSource.id))).scalars().all()
        return [self._src_dict(r) for r in rows]

    async def get_source(self, source_id: int) -> Optional[RssSource]:
        return (await self.db.execute(
            select(RssSource).where(RssSource.id == source_id))).scalars().first()

    async def create_source(self, data: dict) -> dict:
        src = RssSource(**{k: v for k, v in data.items()
                           if hasattr(RssSource, k)})
        self.db.add(src)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(src)
        return self._src_dict(src)

    async def update_source(self, source_id: int, data: dict) -> dict:
        src = await self.get_source(source_id)
        if not src:
            raise ValueError("订阅源不存在")
        for k, v in data.items():
            if hasattr(RssSource, k):
                setattr(src, k, v)
        await self.db.commit()
        await self.db.refresh(src)
        return self._src_dict(src)

    async def delete_source(self, source_id: int) -> bool:
        src = await self.get_source(source_id)
        if not src:
            return False
        await self.db.execute(delete(RssItem).where(RssItem.source_id == source_id))
        await self.db.delete(src)
        await self.db.commit()
        return True

    # ── 网络测试（不写库，或按源写入 net_status）───────────────

    async def test_feed(self, url: str) -> dict:
        if not url:
            return {"ok": False, "count": 0, "sample": [], "error": "订阅地址为空"}
        try:
            items = await self._fetch(url, timeout=12.0)
            return {"ok": True, "count": len(items),
                    "sample": [it.to_dict() for it in items[:3]], "error": ""}
        except Exception as e:
            return {"ok": False, "count": 0, "sample": [], "error": str(e)}

    async def net_test_source(self, source_id: int) -> dict:
        """按订阅源地址测试网络并写回 net_status 字段"""
        src = await self.get_source(source_id)
        if not src:
            raise ValueError("订阅源不存在")
        url = src.url or ""
        await self.db.commit()
        r = await self.test_feed(url)
        src.net_status = f"ok:{r['count']}" if r["ok"] else f"err:{r['error'][:200]}"
        if not r["ok"]:
            src.last_status = f"err:{r['error'][:200]}"
        await self.db.commit()
        return {**r, "net_status": src.net_status}

    async def poll_source(self, source_id: int) -> dict:
        """单独立即轮询单个订阅源（忽略 interval 限频）"""
        src = await self.get_source(source_id)
        if not src:
            raise ValueError("订阅源不存在")
        url = src.url or ""
        if not url:
            raise ValueError("订阅源尚未填写订阅地址")
        await self.db.commit()
        try:
            items = await self._fetch(url, timeout=15.0)
            added = await self._upsert_items(src, items)
            src.last_status = f"ok:{added}"
            src.last_item_count = added
            await self.db.commit()
            await self._prune()
            return {"ok": True, "added": added, "error": ""}
        except Exception as e:
            src.last_status = f"err:{e}"
            await self.db.commit()
            return {"ok": False, "added": 0, "error": str(e)}

    # ── 消息查询（前端 消息滚动 / RSS 专属列表）─────────────────

    async def get_items(self, limit: int = 50, source_id: int | None = None,
                        q: str | None = None, importance: int | None = None,
                        platform: str | None = None) -> list[dict]:
        stmt = select(RssItem)
        if source_id is not None:
            stmt = stmt.where(RssItem.source_id == source_id)
        if importance is not None:
            stmt = stmt.where(RssItem.importance == importance)
        if platform:
            stmt = stmt.where(RssItem.platform == platform)
        if q:
            pat = f"%{q}%"
            stmt = stmt.where(
                RssItem.title.like(pat) | RssItem.summary.like(pat) |
                RssItem.source_name.like(pat))
        stmt = stmt.order_by(RssItem.pub_time.desc().nullslast()).limit(min(limit, 300))
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._item_dict(r) for r in rows]

    async def clear_items(self) -> int:
        """清除所有已入库消息（保留订阅源）"""
        res = await self.db.execute(delete(RssItem))
        _RECENT_ADDED.clear()
        await self.db.commit()
        return res.rowcount or 0

    async def stats(self) -> dict:
        """订阅源与消息总数统计"""
        src_count = (await self.db.execute(
            select(func.count()).select_from(RssSource))).scalar_one()
        enabled = (await self.db.execute(
            select(func.count()).select_from(RssSource)
            .where(RssSource.enabled == True))).scalar_one()  # noqa: E712
        item_count = (await self.db.execute(
            select(func.count()).select_from(RssItem))).scalar_one()
        return {"sources": src_count, "enabled": enabled, "items": item_count,
                "max_items": _MAX_ITEMS_TOTAL}

    async def recent_added(self, limit: int = 50) -> list[dict]:
        """最近入库的增量消息（全局通知用），新→旧"""
        limit = min(max(limit, 1), 200)
        return list(_RECENT_ADDED)[::-1][:limit]

    # ── 轮询引擎（定时任务调用）─────────────────────────────────

    async def poll_sources(self) -> dict:
        """对所有 enabled 源按 interval_min 轮询，返回统计；增量消息进通知队列。
        每个源独立短事务提交，避免长期持锁污染 SQLite 并发写入。"""
        now = datetime.now(_CN_TZ).replace(tzinfo=None)
        sources = (await self.db.execute(
            select(RssSource).where(RssSource.enabled == True))).scalars().all()  # noqa: E712
        polled, added_total, errors = 0, 0, []
        for src in sources:
            if src.last_poll and (now - src.last_poll).total_seconds() < src.interval_min * 60:
                continue
            url = src.url or ""
            if not url:
                continue
            src.last_poll = now
            try:
                await self.db.commit()
                items = await self._fetch(url, timeout=15.0)
                added = await self._upsert_items(src, items)
                src.last_status = f"ok:{added}"
                src.last_item_count = added
                added_total += added
            except Exception as e:
                src.last_status = f"err:{e}"
                errors.append({"id": src.id, "error": str(e)})
            await self.db.commit()
            polled += 1
        await self._prune()
        return {"polled": polled, "added": added_total, "errors": errors}

    # ── 内部方法 ──────────────────────────────────────────────

    async def _fetch(self, url: str, timeout: float = 12.0):
        import asyncio
        return await asyncio.to_thread(fetch_feed, url, timeout)

    async def _upsert_items(self, src: RssSource, items: list) -> int:
        if not items:
            return 0
        existing = set()
        rows = (await self.db.execute(
            select(RssItem.guid).where(RssItem.source_id == src.id)
            .order_by(RssItem.id.desc()).limit(1000))).scalars().all()
        existing.update(rows)
        new_count = 0
        for it in items:
            guid = it.guid or it.link or it.title
            if not guid or guid in existing:
                continue
            item = RssItem(
                source_id=src.id, source_name=src.name, guid=guid,
                title=clean_html(it.title), summary=clean_html(it.summary or "")[:2000],
                link=it.link, author=it.author,
                pub_time=it.pub_time, platform="generic",
                tags=src.tags or [], is_st=bool(it.is_st), importance=it.importance)
            self.db.add(item)
            existing.add(guid)
            new_count += 1
            _RECENT_ADDED.append({
                "guid": guid, "source_id": src.id, "source_name": src.name,
                "title": clean_html(it.title), "link": it.link,
                "pub_time": it.pub_time.isoformat() if it.pub_time else None,
                "importance": it.importance or 3,
            })
        # flush 使 item.id 可用（通知里需要 id 去重）
        try:
            await self.db.flush()
        except Exception:
            pass
        return new_count

    async def _prune(self):
        retention_days = get_setting_int("rsshub_item_retention_days", 30)
        cutoff = datetime.now(_CN_TZ).replace(tzinfo=None) - timedelta(days=retention_days)
        try:
            await self.db.execute(
                delete(RssItem).where(RssItem.created_at < cutoff))
            subq = (select(RssItem.id).order_by(RssItem.id.desc())
                    .limit(_MAX_ITEMS_PER_SOURCE * 2))
            sources = (await self.db.execute(
                select(RssSource.id))).scalars().all()
            for sid in sources:
                ids = (await self.db.execute(
                    select(RssItem.id).where(RssItem.source_id == sid)
                    .order_by(RssItem.id.desc()).limit(_MAX_ITEMS_PER_SOURCE)
                )).scalars().all()
                if ids:
                    await self.db.execute(
                        delete(RssItem).where(
                            RssItem.source_id == sid, RssItem.id.notin_(ids)))
            # 全局上限：超过 _MAX_ITEMS_TOTAL 时删最旧的部分
            total = (await self.db.execute(
                select(func.count()).select_from(RssItem))).scalar_one()
            if total > _MAX_ITEMS_TOTAL:
                keep = (await self.db.execute(
                    select(RssItem.id).order_by(RssItem.id.desc())
                    .limit(_MAX_ITEMS_TOTAL))).scalars().all()
                if keep:
                    await self.db.execute(
                        delete(RssItem).where(RssItem.id.notin_(list(keep))))
        except Exception as e:
            logger.warning(f"RSS prune failed: {e}")

    @staticmethod
    def _src_dict(r: RssSource) -> dict:
        return {
            "id": r.id, "name": r.name, "rss_type": r.rss_type,
            "url": r.url, "base": getattr(r, "base", "") or "",
            "tags": r.tags or [], "remark": r.remark or "",
            "enabled": r.enabled, "interval_min": r.interval_min,
            "net_status": r.net_status or "untested",
            "last_poll": r.last_poll.isoformat() if r.last_poll else None,
            "last_status": r.last_status, "last_item_count": r.last_item_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    @staticmethod
    def _item_dict(r: RssItem) -> dict:
        return {
            "id": r.id, "source_id": r.source_id, "source_name": r.source_name,
            "guid": r.guid, "title": clean_text(r.title or ""),
            "summary": clean_text(r.summary or ""),
            "link": r.link, "author": r.author,
            "pub_time": r.pub_time.isoformat() if r.pub_time else None,
            "platform": r.platform, "tags": r.tags or [],
            "is_st": r.is_st, "importance": r.importance,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }


async def seed_default_sources(db: AsyncSession):
    """部署/空库时写入默认订阅源"""
    count = (await db.execute(select(func.count()).select_from(RssSource))).scalar_one()
    if count:
        return
    defaults = [
        # HTTP/HTTPS 直接 RSS —— 炒股 / IT / 科技
        dict(name="雪球热帖（财经）", rss_type="http",
             url="https://xueqiu.com/hots/topic/rss", tags=["财经"], remark="雪球每日热门话题",
             interval_min=5, enabled=True),
        dict(name="IT之家（IT数码）", rss_type="http",
             url="https://www.ithome.com/rss/", tags=["IT", "数码"], remark="IT 新闻",
             interval_min=5, enabled=True),
        dict(name="爱范儿（数码消费）", rss_type="http",
             url="https://www.ifanr.com/feed", tags=["数码", "科技"], remark="",
             interval_min=10, enabled=True),
        dict(name="钛媒体 TMT（科技商业）", rss_type="http",
             url="https://www.tmtpost.com/rss", tags=["TMT", "科技"], remark="",
             interval_min=10, enabled=True),
        # RSSHub 本地 Docker（127.0.0.1:11200 为宿主机映射）
        dict(name="36氪快讯（本地 RSSHub）", rss_type="rsshub_local",
             url="http://127.0.0.1:11200/36kr/newsflashes", tags=["快讯", "创投"], remark="本地 RSSHub /36kr/newsflashes",
             interval_min=5, enabled=True),
        dict(name="财联社电报（本地 RSSHub）", rss_type="rsshub_local",
             url="http://127.0.0.1:11200/cls/telegraph", tags=["电报", "财经"], remark="本地 RSSHub /cls/telegraph",
             interval_min=5, enabled=True),
        dict(name="财联社深度（本地 RSSHub）", rss_type="rsshub_local",
             url="http://127.0.0.1:11200/cls/depth", tags=["财经", "深度"], remark="本地 RSSHub /cls/depth",
             interval_min=10, enabled=True),
        dict(name="金十快讯（本地 RSSHub）", rss_type="rsshub_local",
             url="http://127.0.0.1:11200/jin10/index", tags=["快讯", "财经"], remark="本地 RSSHub /jin10/index",
             interval_min=5, enabled=True),
        dict(name="华尔街见闻要闻（本地 RSSHub）", rss_type="rsshub_local",
             url="http://127.0.0.1:11200/wallstreetcn/news", tags=["财经"], remark="本地 RSSHub /wallstreetcn/news",
             interval_min=5, enabled=True),
        dict(name="财新网要闻（本地 RSSHub）", rss_type="rsshub_local",
             url="http://127.0.0.1:11200/caixin/latest", tags=["财经"], remark="本地 RSSHub /caixin/latest",
             interval_min=10, enabled=True),
    ]
    for d in defaults:
        db.add(RssSource(**d))
    await db.commit()