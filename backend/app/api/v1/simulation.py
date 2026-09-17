"""模拟交易接口"""
from datetime import timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.simulation.engine import SimulationEngine, _fmt_cst
from app.models.simulation import SimulationAccount, SimulationTrade, SimulationReview
from app.schemas.common import SimulationAccountCreate, SimulationRunRequest

router = APIRouter(prefix="/api/v1/simulation", tags=["模拟交易"])


@router.get("/accounts")
async def accounts(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SimulationAccount).where(
        SimulationAccount.is_active == True).order_by(SimulationAccount.id))).scalars().all()  # noqa: E712
    return [{"id": a.id, "name": a.name, "initial_capital": float(a.initial_capital),
             "current_capital": float(a.current_capital), "total_return": float(a.total_return),
             "max_drawdown": float(a.max_drawdown), "total_trades": a.total_trades,
             "win_rate": float(a.win_rate), "is_active": a.is_active,
             "agent_config_id": a.agent_config_id} for a in rows]


@router.post("/accounts")
async def create_account(body: SimulationAccountCreate, db: AsyncSession = Depends(get_db)):
    engine = SimulationEngine(db)
    aid = await engine.create_account(0, body.name, body.agent_config_id,
                                      body.initial_capital, body.prompt_template, body.rules)
    return {"id": aid}


@router.post("/accounts/init-ai")
async def init_ai_accounts(db: AsyncSession = Depends(get_db)):
    """按三个默认智能体（投研/短线/波段）一键创建 AI 模拟账户并自动执行当日交易"""
    from app.core.agent.registry import get_agent_configs
    engine = SimulationEngine(db)
    configs = await get_agent_configs(db, 0)
    mapping = {"research": "AI-投研账户", "short_term": "AI-短线账户", "swing": "AI-波段账户"}
    created, ran = [], []
    for at, display in mapping.items():
        cfg = next((c for c in configs if c.get("agent_type") == at), None)
        if not cfg:
            continue
        exists = (await db.execute(
            select(SimulationAccount).where(
                SimulationAccount.user_id == 0, SimulationAccount.is_active == True,  # noqa: E712
                SimulationAccount.agent_config_id == cfg.get("id")))).scalars().first()
        aid = exists.id if exists else await engine.create_account(0, display, cfg.get("id"), 100000)
        if not exists:
            created.append({"id": aid, "name": display, "agent_type": at})
        r = await engine.run_daily(aid)
        ran.append({"id": aid, "agent_type": at, "trades": len(r.get("trades", [])),
                    "error": r.get("error")})
    return {"created": created, "ran": ran}


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: int, db: AsyncSession = Depends(get_db)):
    from app.models.simulation import SimulationPosition, SimulationReview, SimulationLog
    a = (await db.execute(select(SimulationAccount).where(SimulationAccount.id == account_id))).scalars().first()
    if not a:
        raise HTTPException(404, "account not found")
    # 硬删除：连同持仓/交易/复盘/日志一并清除，重新创建即为全新账户
    for m in (SimulationPosition, SimulationTrade, SimulationReview, SimulationLog):
        await db.execute(m.__table__.delete().where(m.account_id == account_id))
    await db.delete(a)
    await db.commit()
    return {"ok": True}


@router.post("/accounts/{account_id}/reset")
async def reset_account(account_id: int, db: AsyncSession = Depends(get_db)):
    """重置模拟账户：清空持仓/交易/复盘/日志，资金回到初始值，保留智能体配置与自选池"""
    engine = SimulationEngine(db)
    ok = await engine.reset_account(account_id)
    if not ok:
        raise HTTPException(404, "account not found")
    return {"ok": True}


@router.get("/accounts/{account_id}/stats")
async def stats(account_id: int, db: AsyncSession = Depends(get_db)):
    try:
        engine = SimulationEngine(db)
        return await engine.get_stats(account_id)
    except Exception as e:
        import traceback
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={"error": "stats_failed", "message": str(e),
                     "traceback": traceback.format_exc().splitlines()[-20:]},
        )


@router.get("/accounts/{account_id}/positions")
async def positions(account_id: int, db: AsyncSession = Depends(get_db)):
    from app.models.simulation import SimulationPosition
    rows = (await db.execute(select(SimulationPosition).where(SimulationPosition.account_id == account_id))).scalars().all()
    return [{"symbol": p.symbol, "name": p.name, "quantity": p.quantity,
             "avg_cost": float(p.avg_cost), "current_price": float(p.current_price or 0),
             "unrealized_pnl": float(p.unrealized_pnl or 0)} for p in rows]


@router.get("/accounts/{account_id}/trades")
async def trades(account_id: int, limit: int = 100, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SimulationTrade).where(SimulationTrade.account_id == account_id)
                             .order_by(SimulationTrade.id.desc()).limit(limit))).scalars().all()
    return [{"id": t.id, "symbol": t.symbol, "name": t.name, "action": t.action,
             "quantity": t.quantity, "price": float(t.price), "amount": float(t.amount),
             "fee": float(t.fee), "reason": t.reason, "confidence": float(t.confidence or 0),
             "timestamp": _fmt_cst(t.timestamp)} for t in rows]


@router.get("/accounts/{account_id}/performance")
async def performance(account_id: int, db: AsyncSession = Depends(get_db)):
    engine = SimulationEngine(db)
    return await engine.get_performance(account_id)


@router.get("/accounts/{account_id}/equity")
async def equity(account_id: int, db: AsyncSession = Depends(get_db)):
    engine = SimulationEngine(db)
    return await engine.get_equity_curve(account_id)


@router.get("/accounts/{account_id}/reviews")
async def reviews(account_id: int, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SimulationReview).where(SimulationReview.account_id == account_id)
                             .order_by(SimulationReview.date.desc()).limit(30))).scalars().all()
    return [{"date": r.date.isoformat(), "summary": r.summary, "mistakes": r.mistakes,
             "improvements": r.improvements} for r in rows]


@router.get("/accounts/{account_id}/logs")
async def logs(account_id: int, limit: int = 100, db: AsyncSession = Depends(get_db)):
    engine = SimulationEngine(db)
    return await engine.get_logs(account_id, limit)


@router.post("/accounts/{account_id}/run")
async def run_daily(account_id: int, body: SimulationRunRequest, db: AsyncSession = Depends(get_db)):
    engine = SimulationEngine(db)
    return await engine.run_daily(account_id, body.date, window="手动")


@router.get("/accounts/{account_id}/pool")
async def pool(account_id: int, db: AsyncSession = Depends(get_db)):
    engine = SimulationEngine(db)
    return await engine.get_pool(account_id)


@router.put("/accounts/{account_id}/pool")
async def set_pool(account_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    engine = SimulationEngine(db)
    return await engine.set_pool(account_id, body.get("tracked") or [])