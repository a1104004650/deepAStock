"""RSSHub 订阅服务 - CRUD + 轮询去重 + 消息查询"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rss import RssSource, RssItem
from app.core.settings import get_setting, get_setting_int
from app.core.rsshub.parser import fetch_feed
from app.utils.logger import logger

_CN_TZ = timezone(timedelta(hours=8))
_MAX_ITEMS_PER_SOURCE = 500


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

    # ── 单源测试（不写库）──────────────────────────────────────

    async def test_feed(self, url: str) -> dict:
        try:
            items = await self._fetch(url, timeout=12.0)
            return {"ok": True, "count": len(items),
                    "sample": [it.to_dict() for it in items[:3]], "error": ""}
        except Exception as e:
            return {"ok": False, "count": 0, "sample": [], "error": str(e)}

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
        stmt = stmt.order_by(RssItem.pub_time.desc().nullslast()).limit(min(limit, 200))
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._item_dict(r) for r in rows]

    # ── 轮询引擎（定时任务调用）─────────────────────────────────

    async def poll_sources(self) -> dict:
        """对所有 enabled 源按 interval 轮询，返回统计"""
        from app.core.rsshub import parser as _p
        base = get_setting("rsshub_base", "http://127.0.0.1:1200")
        now = datetime.now(_CN_TZ).replace(tzinfo=None)
        sources = (await self.db.execute(
            select(RssSource).where(RssSource.enabled == True))).scalars().all()  # noqa: E712
        polled, added_total, errors = 0, 0, []
        for src in sources:
            if src.last_poll and (now - src.last_poll).total_seconds() < src.interval_sec:
                continue
            url = src.url or (base.rstrip("/") + (src.route or ""))
            if not url:
                continue
            try:
                items = await self._fetch(url, timeout=15.0)
                added = await self._upsert_items(src, items)
                src.last_status = f"ok:{added}"
                src.last_item_count = added
                added_total += added
            except Exception as e:
                src.last_status = f"err:{e}"
                errors.append({"id": src.id, "error": str(e)})
            src.last_poll = now
            polled += 1
        if polled:
            await self.db.commit()
        # 过期清理
        await self._prune()
        return {"polled": polled, "added": added_total, "errors": errors}

    # ── 内部方法 ──────────────────────────────────────────────

    async def _fetch(self, url: str, timeout: float = 12.0):
        # 同步解析桥接
        import asyncio
        return await asyncio.to_thread(fetch_feed, url, timeout)

    async def _upsert_items(self, src: RssSource, items: list) -> int:
        if not items:
            return 0
        # 加载已有 guid 集合（最近 1000 条即可，足够去重）
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
            is_st = bool(it.is_st)
            if src.filter_st and is_st:
                continue
            item = RssItem(
                source_id=src.id, source_name=src.name, guid=guid,
                title=it.title, summary=(it.summary or "")[:2000],
                link=it.link, author=it.author,
                pub_time=it.pub_time, platform=src.platform,
                tags=src.tags or [], is_st=is_st, importance=it.importance)
            self.db.add(item)
            existing.add(guid)
            new_count += 1
        return new_count

    async def _prune(self):
        """清理过期 + 超限条目"""
        retention_days = get_setting_int("rsshub_item_retention_days", 30)
        cutoff = datetime.now(_CN_TZ).replace(tzinfo=None) - timedelta(days=retention_days)
        try:
            await self.db.execute(
                delete(RssItem).where(RssItem.created_at < cutoff))
            # 每源上限 _MAX_ITEMS_PER_SOURCE，删除多余老记录
            subq = (select(RssItem.id).order_by(RssItem.id.desc())
                    .limit(_MAX_ITEMS_PER_SOURCE * 2))
            # SQLite 不支持 LIMIT in subquery for IN; 用批量 fetch 然后逐源 delete
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
        except Exception as e:
            logger.warning(f"RSS prune failed: {e}")

    @staticmethod
    def _src_dict(r: RssSource) -> dict:
        return {
            "id": r.id, "name": r.name, "platform": r.platform,
            "route": r.route, "url": r.url, "tags": r.tags or [],
            "enabled": r.enabled, "interval_sec": r.interval_sec,
            "filter_st": r.filter_st,
            "last_poll": r.last_poll.isoformat() if r.last_poll else None,
            "last_status": r.last_status, "last_item_count": r.last_item_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    @staticmethod
    def _item_dict(r: RssItem) -> dict:
        return {
            "id": r.id, "source_id": r.source_id, "source_name": r.source_name,
            "guid": r.guid, "title": r.title, "summary": r.summary,
            "link": r.link, "author": r.author,
            "pub_time": r.pub_time.isoformat() if r.pub_time else None,
            "platform": r.platform, "tags": r.tags or [],
            "is_st": r.is_st, "importance": r.importance,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }