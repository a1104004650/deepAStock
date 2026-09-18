"""复盘引擎 - 每日盘后生成复盘报告"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.market.quote_service import MarketService
from app.core.datasource.manager import DataSourceManager
from app.core.agent.base import AgentContext
from app.core.agent.executor import AgentExecutor
from app.models.market import ReplayReport, LimitUp
from app.utils.logger import logger

SHANGHAI = ZoneInfo("Asia/Shanghai")


class ReplayGateError(Exception):
    pass


class ReplayEngine:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.market = MarketService(db)
        self.executor = AgentExecutor(db)

    async def resolve_target(self, target_date: date = None) -> date:
        """复盘目标日解析：
        1) 显式指定历史日期 → 直接用（不做时间门禁）；
        2) 未指定（默认今日）→ 17:00(上海)后才允许按“当日”复盘，盘中/午前调用抛 ReplayGateError；
        3) 非交易日（周末/节假日）→ 自动回退至最近一个交易日（如周日→上周五）。
        """
        now = datetime.now(SHANGHAI)
        t = target_date or now.date()
        if not target_date and now.hour < 17:
            raise ReplayGateError(
                f"今日复盘需在 17:00(北京时间)后生成，当前 {now.strftime('%H:%M')}，"
                "可先选择历史交易日进行复盘")
        for _ in range(10):
            if t.weekday() < 5:
                # 日期有真实K线才算交易日（排除法定节假日）
                if t == now.date() and not target_date:
                    return t
                try:
                    dsm = DataSourceManager(self.db)
                    k = await dsm.get_klines("SH000001", "day", start=t - timedelta(days=1), end=t)
                    if k and str((k[-1].get("dt") or ""))[:10] >= t.isoformat():
                        return t
                except Exception as e:
                    logger.warning(f"trading-day check {t} failed, assume trading day: {e}")
                    return t
                return t
            t -= timedelta(days=1)
        raise ReplayGateError("未能解析出最近交易日，请手动选择历史日期")

    async def run(self, target_date: date = None) -> dict:
        auto = target_date is None
        target_date = await self.resolve_target(target_date)
        logger.info(f"=== 开始复盘 {target_date} ===")

        # 自动任务（定时器 18:00）：若当天已生成过复盘，不覆盖，保留当天最原始数据。
        # 只有用户手动「生成复盘」（显式传日期）才会重建当天。
        if auto:
            got = (await self.db.execute(select(ReplayReport).where(ReplayReport.date == target_date))).scalars().first()
            if got:
                logger.info(f"当日 {target_date} 复盘已存在，自动任务跳过（保留原始数据）")
                return {"status": "skipped", "date": target_date.isoformat(),
                        "message": "当日复盘已生成，自动任务跳过；如需重建请手动点击「生成复盘」"}

        # 数据采集
        indices = await self.market.get_indices()
        sector_flow = await self.market.get_sector_money_flow()
        limit_up = await self.market.get_limit_up()
        ladder = await self.market.get_limit_up_ladder()
        dragon_tiger = await self.market.get_dragon_tiger()
        distribution = await self.market.get_market_distribution()
        news = await self.market.get_news(20)

        market_summary = {
            "date": target_date.isoformat(),
            "indices": indices[:4],
            "distribution": distribution,
            "limit_up_count": len(limit_up),
            "news": news[:5],
        }

        # 三智能体复盘
        ctx = AgentContext(
            date=target_date.isoformat(),
            market_data={
                "sector_flow": sector_flow,
                "limit_up": limit_up,
                "limit_ladder": ladder,
                "distribution": distribution,
                "news": news,
                "dragon_tiger": dragon_tiger,
            },
        )
        reviews = {}
        for at in ["research", "short_term", "swing"]:
            try:
                result = await self.executor.run(agent_type=at, task="daily_replay", context=ctx)
                reviews[at] = result.model_dump()
            except Exception as e:
                logger.warning(f"agent {at} replay failed: {e}")
                reviews[at] = {"summary": f"复盘失败: {e}", "agent_type": at}

        # 生成次日选股池（基于涨停股 + 板块龙头）
        stock_pool = self._build_stock_pool(limit_up, sector_flow)
        stock_pool = await self._enrich_stock_pool(stock_pool)

        # 组装报告
        report = ReplayReport(
            date=target_date,
            market_summary=market_summary,
            sector_flow=sector_flow,
            limit_analysis={"ladder": ladder, "dragon_tiger": dragon_tiger},
            stock_pool=stock_pool,
            agent_reviews=reviews,
            report_md=self._to_markdown(target_date, market_summary, sector_flow, ladder, stock_pool, reviews),
        )
        existing = (await self.db.execute(select(ReplayReport).where(ReplayReport.date == target_date))).scalars().first()
        if existing:
            existing.market_summary = report.market_summary
            existing.sector_flow = report.sector_flow
            existing.limit_analysis = report.limit_analysis
            existing.stock_pool = report.stock_pool
            existing.agent_reviews = report.agent_reviews
            existing.report_md = report.report_md
            existing.report_html = report.report_html
            report = existing
        else:
            self.db.add(report)
        await self.db.commit()

        logger.info(f"=== 复盘完成 {target_date}, 选股池 {len(stock_pool)} 只 ===")
        return {"status": "success", "date": target_date.isoformat(), "report_id": report.id,
                "stock_pool": stock_pool, "reviews": reviews}

    def _build_stock_pool(self, limit_up: list[dict], sector_flow: list[dict]) -> list[dict]:
        pool = []
        seen = set()
        # 涨停梯队：按连板天数降序
        for item in sorted(limit_up, key=lambda x: -int(x.get("consecutive_days", 1))):
            sym = item.get("symbol")
            if sym and sym not in seen and len(pool) < 8:
                seen.add(sym)
                pool.append({
                    "symbol": sym, "name": item.get("name"),
                    "consecutive_days": item.get("consecutive_days", 1),
                    "sector": item.get("sector"),
                    "reason": item.get("reason") or "涨停强势",
                    "source": "涨停梯队",
                })
        # 板块资金龙头
        for s in sector_flow[:5]:
            if len(pool) >= 12:
                break
            leader = s.get("leader_symbol")
            name = s.get("sector_name", "")
            if not leader:
                continue
            if leader not in seen:
                seen.add(leader)
                pool.append({"symbol": leader, "name": name + "龙头",
                             "consecutive_days": 0, "sector": name,
                             "reason": f"板块净流入 {float(s.get('net_inflow', 0))/1e8:.1f}亿", "source": "板块资金"})
        return pool

    async def _enrich_stock_pool(self, pool: list[dict]) -> list[dict]:
        dsm = DataSourceManager(self.db)
        symbols = [p["symbol"] for p in pool if p.get("symbol")]
        if not symbols:
            return pool
        try:
            rt = await dsm.get_realtime(symbols)
        except Exception:
            rt = {}
        # 获取K线用于形态识别
        kline_cache = {}
        for sym in symbols:
            try:
                kl = await dsm.get_klines(sym, "day")
                if kl:
                    kline_cache[sym] = kl[-20:]  # 最近20根K线
            except Exception:
                pass
        for p in pool:
            info = rt.get(p["symbol"], {})
            p["price"] = info.get("price", 0)
            p["change_pct"] = info.get("change_pct", 0)
            cd = p.get("consecutive_days", 0)
            source = p.get("source", "")
            klines = kline_cache.get(p["symbol"], [])
            pattern = self._detect_pattern(klines, cd, info, p.get("source", ""))
            p["performance"] = pattern["performance"]
            p["suggestion"] = pattern["suggestion"]
            p["pattern_tags"] = pattern.get("tags", [])
        return pool

    @staticmethod
    def _detect_pattern(klines: list, consecutive_days: int, info: dict, source: str = "") -> dict:
        """检测K线形态，返回 performance/suggestion/tags"""
        if consecutive_days >= 4:
            return {"performance": f"强势{consecutive_days}连板", "suggestion": "高度板，注意断板风险，关注封单", "tags": ["连板"]}
        if consecutive_days >= 3:
            return {"performance": f"{consecutive_days}连板晋级", "suggestion": "关注封单强度和量能", "tags": ["连板"]}
        if consecutive_days == 2:
            return {"performance": "2连板晋级", "suggestion": "关注次日竞价强度", "tags": ["连板"]}
        if not klines or len(klines) < 5:
            return {"performance": "板块龙头" if source else "首板涨停", "suggestion": "关注板块持续性", "tags": []}
        closes = [float(k.get("close", 0)) for k in klines]
        opens = [float(k.get("open", 0)) for k in klines]
        highs = [float(k.get("high", 0)) for k in klines]
        lows = [float(k.get("low", 0)) for k in klines]
        last_c = closes[-1]
        last_o = opens[-1]
        last_h = highs[-1]
        last_l = lows[-1]
        tags = []
        # 十字星检测（上下影线长，实体小）
        body = abs(last_c - last_o)
        upper = last_h - max(last_c, last_o)
        lower = min(last_c, last_o) - last_l
        avg_range = sum(h - l for h, l in zip(highs[-5:], lows[-5:])) / 5 if len(highs) >= 5 else 1
        if body < avg_range * 0.15 and lower > body * 2 and last_c > last_o:
            tags.append("十字星")
        # 弱转强：前几日下跌/横盘，今日放量上涨
        if len(closes) >= 5:
            prev_change = (closes[-2] - closes[-3]) / closes[-3] * 100 if closes[-3] else 0
            today_change = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] else 0
            if prev_change < 1 and today_change > 3:
                tags.append("弱转强")
        # 二次回踩支撑：近期有高点回落，再次触及支撑后反弹
        if len(closes) >= 10:
            recent_high = max(closes[-10:-2]) if len(closes) >= 10 else max(closes[:-2])
            recent_low = min(lows[-5:])
            if recent_low < recent_high * 0.9 and last_c > last_o and last_c > recent_low * 1.02:
                tags.append("二次回踩")
        # 底部反转
        if len(closes) >= 5:
            five_day_low = min(lows[-5:])
            if last_c > last_o and last_l <= five_day_low * 1.01 and (last_c - last_l) > (last_h - last_c):
                tags.append("底部反转")
        if "十字星" in tags:
            return {"performance": "十字星反转信号", "suggestion": "关注次日确认，量能配合为佳", "tags": tags}
        if "弱转强" in tags:
            return {"performance": "弱转强信号", "suggestion": "关注量能持续性和板块共振", "tags": tags}
        if "二次回踩" in tags:
            return {"performance": "二次回踩支撑", "suggestion": "支撑有效可关注反弹力度", "tags": tags}
        if "底部反转" in tags:
            return {"performance": "底部反转信号", "suggestion": "关注突破确认和量能放大", "tags": tags}
        return {"performance": "首板涨停", "suggestion": "关注次日竞价和量能", "tags": tags}

    def _to_markdown(self, d: date, summary, sector_flow, ladder, pool, reviews) -> str:
        lines = [f"# 复盘报告 {d}", ""]
        lines.append("## 市场概况")
        for idx in summary.get("indices", []):
            lines.append(f"- {idx.get('name')}: {idx.get('price')} ({idx.get('change_pct')}%)")
        lines.append(f"- 涨跌家数: {summary.get('distribution', {}).get('up_count', 0)}↑ / {summary.get('distribution', {}).get('down_count', 0)}↓")
        lines.append(f"- 涨停: {summary.get('limit_up_count', 0)}")
        lines.append("")
        lines.append("## 板块资金流")
        for s in sector_flow[:10]:
            lines.append(f"- {s.get('sector_name')}: 净流入 {float(s.get('net_inflow', 0)):.0f}")
        lines.append("")
        lines.append("## 涨停梯队")
        for k, v in ladder.get("ladder", {}).items():
            lines.append(f"- {k}连板: " + ", ".join(i.get("name", "") for i in v[:5]))
        lines.append("")
        lines.append("## 次日选股池")
        for p in pool[:12]:
            lines.append(f"- {p.get('symbol')} {p.get('name')}: {p.get('reason')}")
        lines.append("")
        for at, r in reviews.items():
            lines.append(f"## AI复盘 - {at}")
            lines.append(f"- {r.get('summary', '')}")
            lines.append("")
        return "\n".join(lines)

    async def get_latest(self) -> dict:
        rep = (await self.db.execute(select(ReplayReport).order_by(ReplayReport.date.desc()).limit(1))).scalars().first()

        def _is_trading_weekday(d) -> bool:
            return d.weekday() < 5

        today = date.today()
        if not rep:
            return {"status": "empty", "date": today.isoformat(),
                    "message": "尚无复盘报告，交易日 18:00 将自动生成，也可手动点击底部按钮生成"}

        if rep.date.isoformat() != today.isoformat() and _is_trading_weekday(today):
            # 新交易日刚开始（今日尚未生成），不展示旧复盘，提示可重新生成
            return {"status": "pending", "date": today.isoformat(), "latest_date": rep.date.isoformat(),
                    "message": f"今日({today.isoformat()})复盘尚未生成，交易日 18:00 自动复盘，也可现在手动生成",
                    "data": self._serialize(rep)}
        return {"status": "ready", "date": rep.date.isoformat(), "data": self._serialize(rep)}

    async def get_by_date(self, d: date) -> dict:
        rep = (await self.db.execute(select(ReplayReport).where(ReplayReport.date == d))).scalars().first()
        return self._serialize(rep) if rep else None

    async def get_history(self, limit: int = 30) -> list[dict]:
        rows = (await self.db.execute(select(ReplayReport).order_by(ReplayReport.date.desc()).limit(limit))).scalars().all()
        return [{"date": r.date.isoformat(), "id": r.id} for r in rows]

    async def get_trend(self, days: int = 7) -> list[dict]:
        rows = (await self.db.execute(
            select(ReplayReport).order_by(ReplayReport.date.desc()).limit(days)
        )).scalars().all()
        result = []
        prev_limit_up = 0
        for r in reversed(rows):
            ms = r.market_summary or {}
            la = r.limit_analysis or {}
            ladder = (la.get("ladder") or {}).get("ladder") or {}
            total_limit = ms.get("limit_up_count", 0)
            # 跌停数从distribution获取
            dist = ms.get("distribution") or {}
            limit_down = dist.get("limit_down", 0) or dist.get("limit_down_count", 0)
            multi_board = 0
            for k, v in ladder.items():
                if int(k) >= 2:
                    multi_board += len(v)
            consecutive_rate = round(multi_board / total_limit * 100, 1) if total_limit > 0 else 0
            broken = max(0, prev_limit_up - multi_board - (total_limit - multi_board)) if prev_limit_up > 0 else 0
            broken_rate = round(broken / prev_limit_up * 100, 1) if prev_limit_up > 0 else 0
            result.append({
                "date": r.date.isoformat(),
                "limit_up": total_limit,
                "limit_down": limit_down,
                "multi_board": multi_board,
                "consecutive_rate": consecutive_rate,
                "broken_rate": broken_rate,
            })
            prev_limit_up = total_limit
        return result

    @staticmethod
    def _serialize(rep) -> dict:
        return {
            "id": rep.id, "date": rep.date.isoformat(),
            "market_summary": rep.market_summary, "sector_flow": rep.sector_flow,
            "limit_analysis": rep.limit_analysis, "stock_pool": rep.stock_pool,
            "agent_reviews": rep.agent_reviews, "report_md": rep.report_md,
        }