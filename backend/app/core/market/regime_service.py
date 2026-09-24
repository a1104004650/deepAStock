"""可解释的市场周期判断，完全基于现有免费行情与复盘快照。"""
import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.market.quote_service import MarketService
from app.core.replay.engine import ReplayEngine
from app.models.market import ReplayReport
from app.utils import shanghai_now


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _score_snapshot(snapshot: dict) -> dict:
    total = int(snapshot.get("total") or 0)
    up_ratio = float(snapshot.get("up_ratio") or 0)
    limit_up = int(snapshot.get("limit_up") or 0)
    limit_down = int(snapshot.get("limit_down") or 0)
    consecutive_rate = float(snapshot.get("consecutive_rate") or 0)
    max_board = int(snapshot.get("max_board") or 0)
    promotion_rate = snapshot.get("promotion_rate")
    broken_rate = snapshot.get("broken_rate")
    positive_sectors = snapshot.get("positive_sectors")
    sector_count = snapshot.get("sector_count")

    available = {
        "breadth": total > 0,
        "limit_structure": total > 0 or limit_up > 0 or limit_down > 0,
        "continuity": promotion_rate is not None and broken_rate is not None,
        "rotation": bool(sector_count),
    }

    breadth_score = _clamp(50 + (up_ratio - 50) * 2.2) if available["breadth"] else None
    if available["limit_structure"]:
        balance = limit_up / max(limit_up + limit_down, 1) * 100
        limit_score = _clamp(balance * .55 + min(consecutive_rate * 1.25, 30) + min(max_board * 3, 15))
    else:
        limit_score = None
    if available["continuity"]:
        continuity_score = _clamp(float(promotion_rate) * .65 + (100 - float(broken_rate)) * .35)
    else:
        continuity_score = None
    if available["rotation"]:
        rotation_score = _clamp(float(positive_sectors) / max(int(sector_count), 1) * 100)
    else:
        rotation_score = None

    parts = {
        "breadth": {"score": breadth_score, "weight": 35, "available": available["breadth"]},
        "limit_structure": {"score": limit_score, "weight": 30, "available": available["limit_structure"]},
        "continuity": {"score": continuity_score, "weight": 20, "available": available["continuity"]},
        "rotation": {"score": rotation_score, "weight": 15, "available": available["rotation"]},
    }
    used_weight = sum(v["weight"] for v in parts.values() if v["available"])
    weighted = sum(v["score"] * v["weight"] for v in parts.values() if v["available"])
    score = round(weighted / used_weight, 1) if used_weight else None
    confidence = round(used_weight / 100, 2)
    return {"score": score, "confidence": confidence, "parts": parts, "available": available}


def _stage(score: float | None, previous_score: float | None = None) -> dict:
    if score is None:
        return {"code": "unknown", "label": "数据不足", "tone": "neutral"}
    delta = score - previous_score if previous_score is not None else 0
    if score <= 25:
        return {"code": "ice", "label": "冰点", "tone": "cold"}
    if score >= 82:
        return {"code": "climax", "label": "高潮", "tone": "hot"}
    if score >= 65 and delta >= -5:
        return {"code": "markup", "label": "主升", "tone": "hot"}
    if delta >= 5:
        return {"code": "start", "label": "启动", "tone": "warm"}
    if delta <= -7:
        return {"code": "decline", "label": "退潮", "tone": "cold"}
    return {"code": "repair", "label": "修复", "tone": "neutral"}


class MarketRegimeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.market = MarketService(db)
        self.replay = ReplayEngine(db)

    @staticmethod
    def _ladder_sets(ladder_payload: dict) -> tuple[set, set, int, int]:
        ladder = (ladder_payload or {}).get("ladder") or {}
        first, multi, max_board = set(), set(), 0
        for key, values in ladder.items():
            try:
                board = int(key)
            except (TypeError, ValueError):
                continue
            max_board = max(max_board, board)
            for stock in values if isinstance(values, list) else []:
                symbol = stock.get("symbol")
                if not symbol:
                    continue
                (first if board <= 1 else multi).add(symbol)
        return first, multi, max_board, sum(len(v) for v in ladder.values() if isinstance(v, list))

    async def _latest_report(self) -> ReplayReport | None:
        return (await self.db.execute(
            select(ReplayReport).where(ReplayReport.date < date.today())
            .order_by(ReplayReport.date.desc()).limit(1)
        )).scalars().first()

    async def get_current(self) -> dict:
        latest = await self._latest_report()
        distribution, ladder, sector_flow = await asyncio.gather(
            self.market.get_market_distribution(),
            self.market.get_limit_up_ladder(),
            self.market.get_sector_money_flow(),
        )
        distribution = distribution or {}
        ladder = ladder or {}
        sector_flow = sector_flow or []
        first, multi, max_board, ladder_total = self._ladder_sets(ladder)

        prev_first, prev_multi = set(), set()
        previous_score = None
        previous_date = None
        if latest:
            previous_date = latest.date.isoformat()
            previous_ladder = ((latest.limit_analysis or {}).get("ladder") or {})
            prev_first, prev_multi, _, _ = self._ladder_sets(previous_ladder)
            historical = self._history_snapshot(latest)
            previous_score = _score_snapshot(historical)["score"]

        promotion_rate = round(len(prev_first & multi) / len(prev_first) * 100, 1) if prev_first else None
        broken_rate = round(len(prev_multi - multi) / len(prev_multi) * 100, 1) if prev_multi else None
        total = int(distribution.get("total") or 0)
        limit_up = int(distribution.get("limit_up") or ladder_total)
        limit_down = int(distribution.get("limit_down") or 0)
        valid_sectors = [s for s in sector_flow if s.get("sector_name")]
        positive_sectors = sum(1 for s in valid_sectors if float(s.get("net_inflow") or 0) > 0)

        snapshot = {
            "total": total,
            "up_ratio": round(float(distribution.get("up_count") or 0) / total * 100, 1) if total else 0,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "consecutive_rate": round(len(multi) / max(limit_up, 1) * 100, 1),
            "max_board": max_board,
            "promotion_rate": promotion_rate,
            "broken_rate": broken_rate,
            "positive_sectors": positive_sectors,
            "sector_count": len(valid_sectors),
        }
        scored = _score_snapshot(snapshot)
        stage = _stage(scored["score"], previous_score)
        leaders = sorted(valid_sectors, key=lambda s: float(s.get("net_inflow") or 0), reverse=True)[:5]

        signals = []
        if total:
            signals.append(f"上涨占比 {snapshot['up_ratio']:.1f}%")
        if limit_up or limit_down:
            signals.append(f"涨停 {limit_up} / 跌停 {limit_down}")
        if max_board:
            signals.append(f"空间高度 {max_board} 板")
        if promotion_rate is not None:
            signals.append(f"首板晋级率 {promotion_rate:.1f}%")
        if broken_rate is not None:
            signals.append(f"断板率（跨日代理）{broken_rate:.1f}%")

        return {
            "as_of": shanghai_now().isoformat(),
            "trade_date": date.today().isoformat(),
            "stage": stage,
            "score": scored["score"],
            "confidence": scored["confidence"],
            "previous_score": previous_score,
            "previous_date": previous_date,
            "components": {
                "breadth": {**scored["parts"]["breadth"], "up_count": distribution.get("up_count", 0), "down_count": distribution.get("down_count", 0), "flat_count": distribution.get("flat_count", 0), "total": total, "up_ratio": snapshot["up_ratio"]},
                "limit_structure": {**scored["parts"]["limit_structure"], "limit_up": limit_up, "limit_down": limit_down, "first_board": len(first), "multi_board": len(multi), "max_board": max_board, "consecutive_rate": snapshot["consecutive_rate"]},
                "continuity": {**scored["parts"]["continuity"], "promotion_rate": promotion_rate, "broken_rate": broken_rate, "basis": "首板晋级率=昨日首板今日进入连板；断板率=昨日连板今日未留在连板集合（跨日代理，非盘中炸板率）"},
                "rotation": {**scored["parts"]["rotation"], "positive_sectors": positive_sectors, "sector_count": len(valid_sectors), "leaders": [{"name": s.get("sector_name"), "change_pct": s.get("change_pct"), "net_inflow": s.get("net_inflow"), "limit_up": s.get("limit_up_count", 0)} for s in leaders]},
            },
            "signals": signals,
            "data_available": scored["score"] is not None,
            "components_available": scored["available"],
            "methodology": "四分项加权：市场宽度35%、涨停结构30%、接力连续性20%、板块轮动15%；缺失分项不按0分处理，而是降低可信度并按可用权重重算。",
        }

    @staticmethod
    def _history_snapshot(report: ReplayReport) -> dict:
        ms = report.market_summary or {}
        dist = ms.get("distribution") or {}
        la = report.limit_analysis or {}
        ladder = (la.get("ladder") or {}).get("ladder") or {}
        multi = sum(len(v) for k, v in ladder.items() if str(k).isdigit() and int(k) >= 2 and isinstance(v, list))
        max_board = max([int(k) for k in ladder if str(k).isdigit()] or [0])
        limit_up = int(ms.get("limit_up_count") or dist.get("limit_up") or 0)
        total = int(dist.get("total") or 0)
        return {
            "total": total,
            "up_ratio": round(float(dist.get("up_count") or 0) / total * 100, 1) if total else 0,
            "limit_up": limit_up,
            "limit_down": int(dist.get("limit_down") or 0),
            "consecutive_rate": round(multi / max(limit_up, 1) * 100, 1),
            "max_board": max_board,
            "promotion_rate": None,
            "broken_rate": None,
            "positive_sectors": None,
            "sector_count": None,
        }

    async def get_history(self, days: int = 20) -> list[dict]:
        trend = await self.replay.get_trend(days)
        previous_score = None
        result = []
        for row in trend:
            snapshot = {
                "total": row.get("total", 0),
                "up_ratio": row.get("up_ratio", 0),
                "limit_up": row.get("limit_up", 0),
                "limit_down": row.get("limit_down", 0),
                "consecutive_rate": row.get("consecutive_rate", 0),
                "max_board": row.get("max_board", 0),
                "promotion_rate": row.get("promotion_rate") if row.get("has_previous") else None,
                "broken_rate": row.get("broken_rate") if row.get("has_previous") else None,
                "positive_sectors": None,
                "sector_count": None,
            }
            scored = _score_snapshot(snapshot)
            stage = _stage(scored["score"], previous_score)
            result.append({**row, "score": scored["score"], "confidence": scored["confidence"], "stage": stage})
            previous_score = scored["score"]
        return result
