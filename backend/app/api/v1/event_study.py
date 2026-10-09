"""Declarative historical condition-event attribution API."""
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_study import EventStudyEngine
from app.db.session import get_db
from app.models.event_study import EventStudyDefinition
from app.utils import shanghai_now

router = APIRouter(prefix="/api/v1/event-study", tags=["条件归因"])


class UniverseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["cached"] = "cached"
    symbols: list[str] = Field(default_factory=list, max_length=2000)
    max_symbols: int = Field(2000, ge=1, le=2000)
    equity_only: bool = True
    exclude_current_st: bool = True
    exclude_boards: list[Literal["main_sh", "main_sz", "chinext", "star", "beijing", "unknown"]] = Field(default_factory=list)
    min_observed_bars: int = Field(60, ge=0, le=1000)
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)


class ConditionSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str
    min: float | None = None
    max: float | None = None
    streak_min: int | None = None
    streak_max: int | None = None
    days_min: int | None = None
    days_max: int | None = None
    shrinking_volume: bool | None = None
    require_pullback: bool | None = None
    max_drawdown_pct: float | None = None
    direction: str | None = None


class RuleSpec(BaseModel):
    name: str = Field("未命名条件组", max_length=100)
    logic: Literal["all", "any"] = "all"
    conditions: list[ConditionSpec] = Field(min_length=1, max_length=20)


class StudyRequest(BaseModel):
    start_date: date = Field(default_factory=lambda: date.today() - timedelta(days=365))
    end_date: date = Field(default_factory=date.today)
    horizons: list[int] = Field(default_factory=lambda: [1, 3, 7, 30], min_length=1, max_length=10)
    benchmark: str = "SH000300"
    return_basis: Literal["event_close", "next_open"] = "event_close"
    occurrence_policy: Literal["state", "entry", "cooldown"] = "entry"
    cooldown_sessions: int = Field(30, ge=0, le=240)
    universe: UniverseSpec = Field(default_factory=UniverseSpec)
    rule: RuleSpec


class SavedStudyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    config: StudyRequest


@router.get("/capabilities")
async def capabilities(db: AsyncSession = Depends(get_db)):
    return await EventStudyEngine(db).capabilities()


@router.get("/presets")
async def presets():
    return [
        {"key": "three_limit_ups", "name": "连续涨停3天", "description": "事件日收盘时连续3个交易日达到涨停阈值近似",
         "rule": {"name": "连续涨停3天", "logic": "all", "conditions": [{"type": "limit_up_streak", "min": 3, "max": 3}]}},
        {"key": "limit_pullback_shrink", "name": "1-3板后缩量调整2-5日", "description": "1至3个连续涨停结束后，2至5个非涨停交易日严格缩量且收盘低于连板日",
         "rule": {"name": "1-3板后缩量调整2-5日", "logic": "all", "conditions": [{"type": "post_limit_pullback", "streak_min": 1, "streak_max": 3, "days_min": 2, "days_max": 5, "shrinking_volume": True, "require_pullback": True, "max_drawdown_pct": 20}]}},
        {"key": "turnover_board", "name": "换手板", "description": "涨停且历史换手率位于指定区间；字段无覆盖时拒绝计算",
         "rule": {"name": "换手板", "logic": "all", "conditions": [{"type": "turnover_limit_up", "min": 8, "max": 35}]}},
        {"key": "volume_breakout", "name": "放量突破20日高点", "description": "收盘突破前20日最高价，量能高于前20日均量1.5倍且收盘位于日内高位",
         "rule": {"name": "放量突破20日高点", "logic": "all", "conditions": [
             {"type": "breakout_distance", "lookback": 20, "reference": "high", "min": 0, "max": 20},
             {"type": "volume_ratio", "lookback": 20, "min": 1.5, "max": 10},
             {"type": "close_location", "min": 70, "max": 100}]}},
        {"key": "shrink_pullback_ma20", "name": "缩量回踩MA20", "description": "收盘距MA20不超过2%，量能低于前20日均量80%，收盘位于日内中上部",
         "rule": {"name": "缩量回踩MA20", "logic": "all", "conditions": [
             {"type": "ma_distance", "lookback": 20, "min": -2, "max": 2},
             {"type": "volume_ratio", "lookback": 20, "min": 0, "max": 0.8},
             {"type": "close_location", "min": 50, "max": 100}]}},
        {"key": "oversold_rebound", "name": "超跌反弹", "description": "距前60日高点回撤至少25%，事件日涨幅大于3%且收于日内高位",
         "rule": {"name": "超跌反弹", "logic": "all", "conditions": [
             {"type": "drawdown_from_high", "lookback": 60, "min": 25, "max": 80},
             {"type": "change_pct", "min": 3, "max": 20},
             {"type": "close_location", "min": 70, "max": 100}]}},
        {"key": "high_volume_upper_shadow", "name": "高位放量长上影", "description": "位于60日区间高位，量能放大且上影线明显",
         "rule": {"name": "高位放量长上影", "logic": "all", "conditions": [
             {"type": "range_position", "lookback": 60, "min": 80, "max": 120},
             {"type": "volume_ratio", "lookback": 20, "min": 1.5, "max": 10},
             {"type": "upper_shadow_pct", "min": 3, "max": 30}]}},
        {"key": "first_board_proxy", "name": "20日内首板近似", "description": "事件日达到涨停阈值，前20个交易日没有涨停阈值事件",
         "rule": {"name": "20日内首板近似", "logic": "all", "conditions": [{"type": "first_limit_in_window", "lookback": 20}]}},
        {"key": "limit_break_proxy", "name": "炸板近似", "description": "最高价触及涨停阈值但收盘回落，属于日K近似而非真实开板记录",
         "rule": {"name": "炸板近似", "logic": "all", "conditions": [{"type": "limit_break", "close_gap_bp": 50}]}},
    ]


def _saved(row: EventStudyDefinition) -> dict:
    return {"id": row.id, "name": row.name, "description": row.description,
            "config": row.config or {}, "is_active": row.is_active,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@router.get("/definitions")
async def definitions(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(EventStudyDefinition).where(
        EventStudyDefinition.is_active.is_(True)).order_by(EventStudyDefinition.updated_at.desc())
    )).scalars().all()
    return [_saved(row) for row in rows]


@router.post("/definitions")
async def create_definition(body: SavedStudyRequest, db: AsyncSession = Depends(get_db)):
    row = EventStudyDefinition(name=body.name.strip(), description=body.description,
                               config=body.config.model_dump(mode="json", exclude_none=True))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _saved(row)


@router.put("/definitions/{definition_id}")
async def update_definition(definition_id: int, body: SavedStudyRequest,
                            db: AsyncSession = Depends(get_db)):
    row = await db.get(EventStudyDefinition, definition_id)
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="条件方案不存在")
    row.name, row.description = body.name.strip(), body.description
    row.config = body.config.model_dump(mode="json", exclude_none=True)
    row.updated_at = shanghai_now()
    await db.commit()
    return _saved(row)


@router.delete("/definitions/{definition_id}")
async def delete_definition(definition_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(EventStudyDefinition, definition_id)
    if not row:
        raise HTTPException(status_code=404, detail="条件方案不存在")
    row.is_active = False
    await db.commit()
    return {"ok": True}


@router.post("/run")
async def run_study(body: StudyRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await EventStudyEngine(db).run(body.model_dump(mode="json", exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
