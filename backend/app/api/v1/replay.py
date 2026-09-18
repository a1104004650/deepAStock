"""复盘接口"""
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.replay.engine import ReplayEngine, ReplayGateError
from app.schemas.common import ReplayTriggerRequest

router = APIRouter(prefix="/api/v1/replay", tags=["复盘"])


@router.get("/latest")
async def latest(db: AsyncSession = Depends(get_db)):
    engine = ReplayEngine(db)
    return await engine.get_latest()


@router.get("/history")
async def history(limit: int = 30, db: AsyncSession = Depends(get_db)):
    engine = ReplayEngine(db)
    return await engine.get_history(limit)


@router.get("/trend")
async def trend(days: int = 7, db: AsyncSession = Depends(get_db)):
    engine = ReplayEngine(db)
    return await engine.get_trend(days)


@router.get("/{replay_date}")
async def by_date(replay_date: str, db: AsyncSession = Depends(get_db)):
    try:
        d = date.fromisoformat(replay_date)
    except ValueError:
        return {"error": "invalid date"}
    engine = ReplayEngine(db)
    return await engine.get_by_date(d)


@router.post("/trigger")
async def trigger(body: ReplayTriggerRequest, db: AsyncSession = Depends(get_db)):
    engine = ReplayEngine(db)
    try:
        return await engine.run(body.date)
    except ReplayGateError as e:
        return {"status": "gated", "message": str(e)}