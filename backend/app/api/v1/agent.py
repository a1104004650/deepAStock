"""AI智能体接口"""
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db, SessionLocal
from app.core.agent.registry import get_agent_configs, ensure_default_agents, create_agent
from app.core.agent.executor import AgentExecutor
from app.core.agent.base import AgentContext
from app.core.market.stock_service import StockService
from app.models.agent import AgentConfig, AgentRun, StockAiAnalysis
from app.schemas.common import AgentConfigCreate, AgentConfigUpdate, AgentAnalyzeRequest
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/agents", tags=["AI智能体"])


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")


async def _build_stock_context(db: AsyncSession, symbol: str) -> AgentContext:
    from app.core.czsc_engine.analyzer import CZSCAnalyzer
    stock = StockService(db)
    return AgentContext(
        symbol=symbol,
        financial_data=await stock.get_financial(symbol),
        money_flow=await stock.get_money_flow(symbol),
        sector_info=await stock.get_sector(symbol),
        sentiment=await stock.get_sentiment(symbol),
        market_data={"forms": await stock.get_technic_forms(symbol)},
        czsc_result=await CZSCAnalyzer(db).analyze(symbol, "day"),
        news=await stock.get_stock_news(symbol),
    )


@router.get("/")
async def list_agents(db: AsyncSession = Depends(get_db)):
    await ensure_default_agents(db)
    return await get_agent_configs(db)


@router.post("/")
async def create_agent_config(body: AgentConfigCreate, db: AsyncSession = Depends(get_db)):
    cfg = AgentConfig(**body.model_dump(), user_id=0, is_active=True, is_default=False)
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return {"id": cfg.id, "name": cfg.name, "agent_type": cfg.agent_type}


@router.put("/{agent_id}")
async def update_agent(agent_id: int, body: AgentConfigUpdate, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))).scalars().first()
    if not cfg:
        raise HTTPException(404, "agent not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(cfg, k, v)
    cfg.updated_at = None
    await db.commit()
    return {"ok": True}


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))).scalars().first()
    if not cfg:
        raise HTTPException(404, "agent not found")
    if cfg.is_default:
        raise HTTPException(400, "不能删除默认智能体")
    await db.delete(cfg)
    await db.commit()
    return {"ok": True}


@router.post("/analyze/stock")
async def analyze_stock(body: AgentAnalyzeRequest, db: AsyncSession = Depends(get_db)):
    ctx = await _build_stock_context(db, body.symbol)
    executor = AgentExecutor(db)
    result = await executor.run(agent_type=body.agent_type or "research",
                                agent_config_id=body.agent_config_id,
                                task=body.task, context=ctx)
    return result.model_dump()


async def _brainstorm_one(agent_type: str, symbol: str) -> dict:
    """独立数据库会话并行分析，避免共享 async session 并发冲突"""
    async with SessionLocal() as db:
        ctx = await _build_stock_context(db, symbol)
        executor = AgentExecutor(db)
        result = await executor.run(agent_type=agent_type, task="analyze_stock", context=ctx)
        data = result.model_dump()
        data["agent_type"] = agent_type
        return data


async def _load_cached(symbol: str, db: AsyncSession) -> dict | None:
    row = (await db.execute(
        select(StockAiAnalysis).where(
            StockAiAnalysis.symbol == symbol.upper(),
            StockAiAnalysis.trade_date == _today()).order_by(StockAiAnalysis.id.desc()).limit(1)
    )).scalars().first()
    if not row:
        return None
    return {
        "symbol": row.symbol, "cached": True,
        "analyzed_at": row.created_at.isoformat() if row.created_at else None,
        "agents": row.payload.get("agents", []) if isinstance(row.payload, dict) else [],
    }


async def _save_agent_result(symbol: str, agent_type: str, data: dict) -> None:
    """单个智能体结果合并入库：当日明细按 agent_type 更新，不覆盖其他智能体。"""
    async with SessionLocal() as db:
        row = (await db.execute(
            select(StockAiAnalysis).where(
                StockAiAnalysis.symbol == symbol.upper(),
                StockAiAnalysis.trade_date == _today()).order_by(StockAiAnalysis.id.desc()).limit(1)
        )).scalars().first()
        if row is None:
            row = StockAiAnalysis(symbol=symbol.upper(), trade_date=_today(), payload={"agents": []})
            db.add(row)
        agents = row.payload.get("agents", []) if isinstance(row.payload, dict) else []
        agents = [a for a in agents if a.get("agent_type") != agent_type]
        agents.append(data)
        row.payload = {"agents": agents}
        try:
            await db.commit()
        except Exception:
            await db.rollback()


@router.get("/brainstorm/{symbol}")
async def brainstorm_cached(symbol: str, db: AsyncSession = Depends(get_db)):
    """读取当日已保存的个股 AI 分析（不调用 LLM，切换个股后展示缓存）"""
    cached = await _load_cached(symbol, db)
    if cached:
        return cached
    return {"symbol": symbol.upper(), "cached": False, "agents": [], "analyzed_at": None}


@router.post("/brainstorm")
async def brainstorm_stock(body: AgentAnalyzeRequest, force: bool = False, db: AsyncSession = Depends(get_db)):
    """只分析选定的一个智能体（body.agent_type，默认 research），不再三智能体串行。
    当日该智能体已分析则返回缓存（force=True 重新分析）。"""
    atype = body.agent_type or "research"
    if atype not in ("research", "short_term", "swing"):
        raise HTTPException(400, "agent_type 必须是 research/short_term/swing")
    if not force:
        cached = await _load_cached(body.symbol, db)
        cached_agents = (cached or {}).get("agents", []) or []
        if any((a.get("agent_type") == atype) for a in cached_agents):
            return cached
    try:
        data = await _brainstorm_one(atype, body.symbol)
    except Exception as e:
        logger.warning(f"brainstorm {atype} failed: {e}")
        raise HTTPException(502, f"{atype} 分析失败: {e}")
    if (data.get("summary") or "").strip() and float(data.get("confidence") or 0) >= 0.3:
        try:
            await _save_agent_result(body.symbol, atype, data)
        except Exception:
            pass
    return {"symbol": body.symbol.upper(), "cached": False, "agent_type": atype, **data}


@router.post("/brainstorm/{symbol}/{agent_type}")
async def brainstorm_one(symbol: str, agent_type: str):
    """单个智能体分析单个完整请求，避免多智能体串行超时；命中 0.3 置信度则持久化。"""
    if agent_type not in ("research", "short_term", "swing"):
        raise HTTPException(400, "agent_type 必须是 research/short_term/swing")
    try:
        data = await _brainstorm_one(agent_type, symbol)
    except Exception as e:
        logger.warning(f"brainstorm {agent_type} failed: {e}")
        raise HTTPException(502, f"{agent_type} 分析失败: {e}")
    if (data.get("summary") or "").strip() and float(data.get("confidence") or 0) >= 0.3:
        try:
            await _save_agent_result(symbol, agent_type, data)
        except Exception:
            pass
    return {"symbol": symbol.upper(), "cached": False, "agent_type": agent_type, **data}


@router.post("/analyze/market")
async def analyze_market(agent_type: str = "research", db: AsyncSession = Depends(get_db)):
    from app.core.market.quote_service import MarketService
    market = MarketService(db)
    ctx = AgentContext(
        market_data={"sector_flow": await market.get_sector_money_flow(),
                     "limit_up": await market.get_limit_up()}
    )
    executor = AgentExecutor(db)
    result = await executor.run(agent_type=agent_type, task="daily_replay", context=ctx)
    return result.model_dump()


@router.get("/runs")
async def get_runs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AgentRun).order_by(AgentRun.id.desc()).limit(limit))).scalars().all()
    return [{"id": r.id, "agent_config_id": r.agent_config_id, "task_type": r.task_type,
             "status": r.status, "duration_ms": r.duration_ms,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalars().first()
    if not r:
        raise HTTPException(404, "run not found")
    return {"id": r.id, "task_type": r.task_type, "input_data": r.input_data,
            "output_data": r.output_data, "status": r.status, "error_message": r.error_message,
            "duration_ms": r.duration_ms}


@router.get("/{agent_type}/prompts")
async def get_prompt_history(agent_type: str, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(AgentConfig).where(AgentConfig.agent_type == agent_type, AgentConfig.is_default == True))).scalars().first()
    if not cfg:
        raise HTTPException(404, f"agent {agent_type} not found")
    from app.models.agent import AgentPromptLog
    logs = (await db.execute(
        select(AgentPromptLog).where(AgentPromptLog.agent_type == agent_type)
        .order_by(AgentPromptLog.version.desc()).limit(20)
    )).scalars().all()
    return {
        "current_version": cfg.prompt_version,
        "current_prompt": cfg.system_prompt,
        "history": [{"version": l.version, "reason": l.reason, "score": float(l.performance_score) if l.performance_score else None,
                      "created_at": l.created_at.isoformat() if l.created_at else None} for l in logs],
    }


@router.post("/{agent_type}/prompts/update")
async def update_prompt(agent_type: str, body: dict, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(AgentConfig).where(AgentConfig.agent_type == agent_type, AgentConfig.is_default == True))).scalars().first()
    if not cfg:
        raise HTTPException(404, f"agent {agent_type} not found")
    new_prompt = body.get("system_prompt", "")
    reason = body.get("reason", "手动更新")
    if not new_prompt:
        raise HTTPException(400, "system_prompt 不能为空")
    from app.models.agent import AgentPromptLog
    old_version = cfg.prompt_version or 1
    log = AgentPromptLog(agent_config_id=cfg.id, agent_type=agent_type, version=old_version,
                         system_prompt=cfg.system_prompt, reason=f"v{old_version}备份")
    db.add(log)
    cfg.system_prompt = new_prompt
    cfg.prompt_version = old_version + 1
    history = cfg.prompt_history or []
    history.append({"version": cfg.prompt_version, "reason": reason})
    cfg.prompt_history = history[-50:]
    cfg.updated_at = None
    await db.commit()
    return {"ok": True, "version": cfg.prompt_version}


@router.post("/{agent_type}/prompts/rollback")
async def rollback_prompt(agent_type: str, body: dict, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(AgentConfig).where(AgentConfig.agent_type == agent_type, AgentConfig.is_default == True))).scalars().first()
    if not cfg:
        raise HTTPException(404, f"agent {agent_type} not found")
    target_version = body.get("version")
    if not target_version:
        raise HTTPException(400, "需要指定 version")
    from app.models.agent import AgentPromptLog
    log = (await db.execute(
        select(AgentPromptLog).where(AgentPromptLog.agent_type == agent_type, AgentPromptLog.version == target_version)
    )).scalars().first()
    if not log:
        raise HTTPException(404, f"版本 v{target_version} 不存在")
    current_log = AgentPromptLog(agent_config_id=cfg.id, agent_type=agent_type, version=cfg.prompt_version,
                                  system_prompt=cfg.system_prompt, reason=f"回滚前备份v{cfg.prompt_version}")
    db.add(current_log)
    cfg.system_prompt = log.system_prompt
    cfg.prompt_version = (cfg.prompt_version or 1) + 1
    cfg.updated_at = None
    await db.commit()
    return {"ok": True, "version": cfg.prompt_version}


@router.post("/{agent_type}/evaluate")
async def self_evaluate(agent_type: str, symbol: str, db: AsyncSession = Depends(get_db)):
    """手动触发AI自我评估"""
    async with SessionLocal() as eval_db:
        ctx = await _build_stock_context(eval_db, symbol)
        executor = AgentExecutor(eval_db)
        result = await executor.run(agent_type=agent_type, task="analyze_stock", context=ctx)
        data = result.model_dump()
        eval_result = {
            "agent_type": agent_type, "symbol": symbol,
            "score": data.get("score"), "summary": data.get("summary"),
            "evaluated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
    return eval_result