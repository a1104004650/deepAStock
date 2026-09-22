"""实验室 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, date

from app.db.session import get_db
from app.models.laboratory import (
    LabCompetition, LabParticipant, LabCompPosition, LabCompTrade,
    LabChatMessage, LabLeaderboard, LabResearchTask, LabAnalyst,
    LabAnalystReport, LabResearchReport, LabCompEvent
)
from app.core.lab import CompetitionEngine, ResearchTeamEngine
from app.core.lab.competition import AutoRunEngine, AccountingEngine, CompetitionEngine
from app.utils import shanghai_now

router = APIRouter(prefix="/api/v1/lab", tags=["实验室"])


# ==================== Pydantic 模型 ====================

class CompetitionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    stock_pool: Optional[List[str]] = None
    initial_capital: Optional[float] = 100000.0
    max_position_pct: Optional[float] = 20
    max_positions: Optional[int] = 5
    allow_short: Optional[bool] = False
    trading_fee: Optional[float] = 0.0003
    auto_trade: Optional[bool] = True
    trade_interval_min: Optional[int] = 30
    start_date: Optional[str] = None
    end_date: Optional[str] = None

class CompetitionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    stock_pool: Optional[List[str]] = None
    max_position_pct: Optional[float] = None
    max_positions: Optional[int] = None
    allow_short: Optional[bool] = None
    trading_fee: Optional[float] = None
    auto_trade: Optional[bool] = None
    trade_interval_min: Optional[int] = None

class ParticipantCreate(BaseModel):
    name: str
    avatar: Optional[str] = "🤖"
    provider: str  # openai/deepseek/qwen/zhipu/claude/gemini/ollama
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    system_prompt: Optional[str] = None

class AnalystCreate(BaseModel):
    name: str
    role: str  # value/game/tech/quant/overall
    avatar: Optional[str] = "📊"
    system_prompt: Optional[str] = None
    provider: str
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    sort_order: Optional[int] = 0

class ResearchTaskCreate(BaseModel):
    symbol: str
    stock_name: Optional[str] = None


# ==================== 比赛管理 ====================

@router.get("/competitions")
async def get_competitions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LabCompetition).order_by(desc(LabCompetition.created_at))
    )
    items = result.scalars().all()

    output = []
    for c in items:
        # 统计参赛者数
        pr = await db.execute(
            select(LabParticipant).where(LabParticipant.competition_id == c.id)
        )
        count = len(pr.scalars().all())
        output.append({
            "id": c.id, "name": c.name, "description": c.description,
            "status": c.status, "participant_count": count,
            "initial_capital": c.initial_capital,
            "start_date": c.start_date, "end_date": c.end_date,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return output


@router.get("/competitions/{comp_id}")
async def get_competition(comp_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")

    # 参赛者
    pr = await db.execute(
        select(LabParticipant).where(LabParticipant.competition_id == comp_id)
        .order_by(desc(LabParticipant.total_return))
    )
    participants = pr.scalars().all()

    # 计算每个参赛者的总市值（资金 + 持仓市值）
    p_ids = [p.id for p in participants]
    pos_result = await db.execute(
        select(LabCompPosition).where(LabCompPosition.participant_id.in_(p_ids))
    )
    all_positions = pos_result.scalars().all()
    pos_map = {}
    for pos in all_positions:
        pos_map.setdefault(pos.participant_id, []).append(pos)

    return {
        "id": comp.id, "name": comp.name, "description": comp.description,
        "status": comp.status, "stock_pool": comp.stock_pool,
        "initial_capital": comp.initial_capital,
        "auto_trade": comp.auto_trade,
        "trade_interval_min": comp.trade_interval_min,
        "max_position_pct": comp.max_position_pct,
        "max_positions": comp.max_positions,
        "trading_fee": comp.trading_fee,
        "start_date": comp.start_date, "end_date": comp.end_date,
        "created_at": comp.created_at.isoformat() if comp.created_at else None,
        "participants": [{
            "id": p.id, "name": p.name, "avatar": p.avatar,
            "provider": p.provider, "model_name": p.model_name,
            "api_base": p.api_base, "system_prompt": p.system_prompt,
            "current_capital": p.current_capital, "total_return": p.total_return,
            "total_trades": p.total_trades, "status": p.status,
            "market_value": sum(
                pos.current_price * pos.quantity for pos in pos_map.get(p.id, [])
            ),
            "total_assets": p.current_capital + sum(
                pos.current_price * pos.quantity for pos in pos_map.get(p.id, [])
            ),
            "positions_count": len(pos_map.get(p.id, [])),
        } for p in participants],
    }


@router.post("/competitions")
async def create_competition(data: CompetitionCreate, db: AsyncSession = Depends(get_db)):
    comp = LabCompetition(
        name=data.name,
        description=data.description,
        stock_pool=data.stock_pool,
        initial_capital=data.initial_capital,
        max_position_pct=(data.max_position_pct or 20) / 100,
        max_positions=data.max_positions,
        allow_short=data.allow_short,
        trading_fee=data.trading_fee,
        auto_trade=data.auto_trade,
        trade_interval_min=data.trade_interval_min,
        start_date=data.start_date,
        end_date=data.end_date,
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return {"id": comp.id, "message": "创建成功"}


@router.put("/competitions/{comp_id}/start")
async def start_competition(comp_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")
    if comp.status != "setup":
        raise HTTPException(status_code=400, detail="比赛已启动或已结束")

    comp.status = "active"
    if not comp.start_date:
        comp.start_date = date.today().isoformat()
    await db.commit()

    engine = CompetitionEngine(db)
    await engine.post_system_message(comp_id, f"比赛「{comp.name}」正式开始！")

    return {"message": "比赛已开始"}


@router.put("/competitions/{comp_id}/finish")
async def finish_competition(comp_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")

    await AutoRunEngine().stop(comp_id)
    comp.status = "finished"
    comp.end_date = date.today().isoformat()
    await db.commit()

    engine = AccountingEngine(db)
    await engine.update_leaderboard(comp_id)
    await CompetitionEngine(db).post_system_message(comp_id, f"比赛「{comp.name}」已结束！最终排行榜已更新。")

    return {"message": "比赛已结束"}


@router.put("/competitions/{comp_id}/reset")
async def reset_competition(comp_id: int, db: AsyncSession = Depends(get_db)):
    """重置比赛：清除所有交易、持仓、聊天、排行榜，回到初始状态"""
    # 先停止AI自主运行
    await AutoRunEngine().stop(comp_id)

    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")

    # 获取所有参赛者
    pr = await db.execute(
        select(LabParticipant).where(LabParticipant.competition_id == comp_id)
    )
    participants = pr.scalars().all()

    for p in participants:
        # 清除持仓
        await db.execute(delete(LabCompPosition).where(LabCompPosition.participant_id == p.id))
        # 清除交易
        await db.execute(delete(LabCompTrade).where(LabCompTrade.participant_id == p.id))
        # 重置参赛者数据
        p.current_capital = comp.initial_capital
        p.total_return = 0.0
        p.total_trades = 0
        p.win_rate = 0.0
        p.max_drawdown = 0.0

    # 清除聊天
    await db.execute(delete(LabChatMessage).where(LabChatMessage.competition_id == comp_id))
    # 清除排行榜
    await db.execute(delete(LabLeaderboard).where(LabLeaderboard.competition_id == comp_id))

    # 重置比赛
    comp.status = "setup"
    comp.total_rounds = 0
    comp.start_date = None
    comp.end_date = None
    comp.paused_at = None
    await db.commit()

    engine = CompetitionEngine(db)
    await engine.post_system_message(comp_id, f"比赛已重置，所有数据已清空。")

    return {"message": "比赛已重置"}


@router.put("/competitions/{comp_id}/pause")
async def pause_competition(comp_id: int, db: AsyncSession = Depends(get_db)):
    """暂停比赛"""
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")
    if comp.status != "active":
        raise HTTPException(status_code=400, detail="只能暂停进行中的比赛")

    await AutoRunEngine().stop(comp_id)
    comp.status = "paused"
    comp.paused_at = shanghai_now()
    await db.commit()

    engine = CompetitionEngine(db)
    await engine.post_system_message(comp_id, f"比赛已暂停。")

    return {"message": "比赛已暂停"}


@router.put("/competitions/{comp_id}/resume")
async def resume_competition(comp_id: int, db: AsyncSession = Depends(get_db)):
    """恢复比赛"""
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")
    if comp.status != "paused":
        raise HTTPException(status_code=400, detail="只能恢复已暂停的比赛")

    comp.status = "active"
    comp.paused_at = None
    await db.commit()

    engine = CompetitionEngine(db)
    await engine.post_system_message(comp_id, f"比赛已恢复，继续进行！")

    return {"message": "比赛已恢复"}


@router.put("/competitions/{comp_id}")
async def update_competition(comp_id: int, data: CompetitionUpdate, db: AsyncSession = Depends(get_db)):
    """更新比赛设置"""
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")

    update_data = data.model_dump(exclude_unset=True)
    # 百分比转小数
    if "max_position_pct" in update_data and update_data["max_position_pct"] is not None:
        update_data["max_position_pct"] = update_data["max_position_pct"] / 100

    for k, v in update_data.items():
        if v is not None:
            setattr(comp, k, v)
    await db.commit()
    return {"message": "更新成功"}


@router.delete("/competitions/{comp_id}")
async def delete_competition(comp_id: int, db: AsyncSession = Depends(get_db)):
    # 先停止AI自主运行
    await AutoRunEngine().stop(comp_id)
    # 级联删除
    await db.execute(delete(LabChatMessage).where(LabChatMessage.competition_id == comp_id))
    await db.execute(delete(LabLeaderboard).where(LabLeaderboard.competition_id == comp_id))
    await db.execute(delete(LabCompEvent).where(LabCompEvent.competition_id == comp_id))

    result = await db.execute(select(LabParticipant).where(LabParticipant.competition_id == comp_id))
    participants = result.scalars().all()
    for p in participants:
        await db.execute(delete(LabCompPosition).where(LabCompPosition.participant_id == p.id))
        await db.execute(delete(LabCompTrade).where(LabCompTrade.participant_id == p.id))
    await db.execute(delete(LabParticipant).where(LabParticipant.competition_id == comp_id))
    await db.execute(delete(LabCompetition).where(LabCompetition.id == comp_id))
    await db.commit()

    return {"message": "已删除"}


# ==================== 参赛者管理 ====================

@router.post("/competitions/{comp_id}/participants")
async def add_participant(comp_id: int, data: ParticipantCreate, db: AsyncSession = Depends(get_db)):
    # 获取比赛初始资金
    comp_result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = comp_result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")

    p = LabParticipant(
        competition_id=comp_id,
        name=data.name,
        avatar=data.avatar,
        provider=data.provider,
        api_base=data.api_base,
        api_key=data.api_key,
        model_name=data.model_name,
        system_prompt=data.system_prompt,
        initial_capital=comp.initial_capital,
        current_capital=comp.initial_capital,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)

    engine = CompetitionEngine(db)
    await engine.post_system_message(comp_id, f"新选手 {data.name} 加入比赛！")

    return {"id": p.id, "message": "添加成功"}


@router.delete("/participants/{participant_id}")
async def remove_participant(participant_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LabParticipant).where(LabParticipant.id == participant_id))
    p = result.scalars().first()
    if not p:
        raise HTTPException(status_code=404, detail="参赛者不存在")

    await db.execute(delete(LabCompPosition).where(LabCompPosition.participant_id == participant_id))
    await db.execute(delete(LabCompTrade).where(LabCompTrade.participant_id == participant_id))
    await db.execute(delete(LabChatMessage).where(LabChatMessage.participant_id == participant_id))
    await db.execute(delete(LabParticipant).where(LabParticipant.id == participant_id))
    await db.commit()


@router.put("/participants/{participant_id}")
async def update_participant(participant_id: int, data: ParticipantCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LabParticipant).where(LabParticipant.id == participant_id))
    p = result.scalars().first()
    if not p:
        raise HTTPException(status_code=404, detail="参赛者不存在")
    update_data = data.model_dump(exclude_unset=True)
    if not update_data.get("api_key"):
        update_data.pop("api_key", None)
    if not update_data.get("api_base"):
        update_data.pop("api_base", None)
    if not update_data.get("system_prompt"):
        update_data.pop("system_prompt", None)
    for k, v in update_data.items():
        setattr(p, k, v)
    await db.commit()
    return {"message": "更新成功"}


@router.post("/participants/{participant_id}/check-health")
async def check_participant_ai_health(participant_id: int, db: AsyncSession = Depends(get_db)):
    """检查参赛者AI连接健康状态"""
    from app.core.agent.llm_client import LLMClient
    import time

    result = await db.execute(select(LabParticipant).where(LabParticipant.id == participant_id))
    p = result.scalars().first()
    if not p:
        raise HTTPException(status_code=404, detail="参赛者不存在")

    start = time.time()
    try:
        llm = LLMClient(
            provider=p.provider,
            api_base=p.api_base,
            api_key=p.api_key,
            model=p.model_name,
        )
        reply = await llm.complete("回复ok", "你是一个测试机器人，只回复ok两个字。")
        latency_ms = int((time.time() - start) * 1000)
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "model": p.model_name,
            "provider": p.provider,
            "reply": (reply or "")[:50],
        }
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "error": str(e)[:200],
            "model": p.model_name,
            "provider": p.provider,
        }


# ==================== 比赛交易 ====================

@router.post("/competitions/{comp_id}/trade-all")
async def trigger_all_trades(
    comp_id: int,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """触发所有参赛者交易一轮

    Args:
        force: 是否强制执行（跳过交易时段检查）
    """
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")
    if comp.status != "active":
        raise HTTPException(status_code=400, detail="比赛未在进行中")

    pr = await db.execute(
        select(LabParticipant).where(
            LabParticipant.competition_id == comp_id,
            LabParticipant.status == "active"
        )
    )
    participants = pr.scalars().all()

    engine = CompetitionEngine(db)
    results = []
    for p in participants:
        r = await engine.run_participant_trading(p.id, force=force)
        results.append({"name": p.name, **r})

    comp.total_rounds += 1
    await db.commit()

    return {"message": f"已触发{len(results)}名选手交易", "results": results}


@router.post("/competitions/{comp_id}/participants/{participant_id}/trade")
async def trigger_single_trade(comp_id: int, participant_id: int, db: AsyncSession = Depends(get_db)):
    """触发单个参赛者交易"""
    # 校验参赛者属于该比赛
    pr = await db.execute(select(LabParticipant).where(LabParticipant.id == participant_id))
    p = pr.scalars().first()
    if not p or p.competition_id != comp_id:
        raise HTTPException(status_code=404, detail="参赛者不存在或不属于该比赛")
    engine = CompetitionEngine(db)
    result = await engine.run_participant_trading(participant_id, force=True)
    return result


@router.post("/competitions/{comp_id}/chat-all")
async def trigger_all_chat(comp_id: int, db: AsyncSession = Depends(get_db)):
    """触发所有参赛者发表市场分析（不交易）"""
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")
    if comp.status != "active":
        raise HTTPException(status_code=400, detail="比赛未在进行中")

    pr = await db.execute(
        select(LabParticipant).where(
            LabParticipant.competition_id == comp_id,
            LabParticipant.status == "active"
        )
    )
    participants = pr.scalars().all()

    engine = CompetitionEngine(db)
    results = []
    for p in participants:
        r = await engine.run_chat_only(p.id)
        results.append({"name": p.name, **r})

    return {"message": f"已触发{len(results)}名选手发言", "results": results}


@router.post("/competitions/{comp_id}/auto-trade-run")
async def run_auto_trade_round(comp_id: int, db: AsyncSession = Depends(get_db)):
    """执行一轮自动交易（旧接口，保留兼容）"""
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")
    if comp.status != "active" or not comp.auto_trade:
        return {"message": "比赛未开启自动交易"}

    pr = await db.execute(
        select(LabParticipant).where(
            LabParticipant.competition_id == comp_id,
            LabParticipant.status == "active"
        )
    )
    participants = pr.scalars().all()

    engine = CompetitionEngine(db)
    results = []
    for p in participants:
        r = await engine.run_participant_trading(p.id, force=True)
        results.append({"name": p.name, **r})

    comp.total_rounds += 1
    await db.commit()

    return {"message": f"自动交易完成，{len(results)}名选手", "results": results}


# ==================== AI自主运行 ====================

@router.post("/competitions/{comp_id}/ai-start")
async def start_ai_auto_run(comp_id: int, db: AsyncSession = Depends(get_db)):
    """启动AI自主运行：所有选手在后台自主交易+发言"""
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")
    if comp.status != "active":
        raise HTTPException(status_code=400, detail="比赛未在进行中")

    from app.db.session import SessionLocal
    engine = AutoRunEngine()
    ret = await engine.start(comp_id, SessionLocal)
    if not ret.get("ok"):
        raise HTTPException(status_code=400, detail=ret.get("error", "启动失败"))

    return {"message": "AI自主运行已启动"}


@router.post("/competitions/{comp_id}/ai-stop")
async def stop_ai_auto_run(comp_id: int, db: AsyncSession = Depends(get_db)):
    """停止AI自主运行"""
    engine = AutoRunEngine()
    await engine.stop(comp_id)

    return {"message": "AI自主运行已停止"}


@router.get("/competitions/{comp_id}/ai-status")
async def get_ai_auto_run_status(comp_id: int):
    """获取AI自主运行状态"""
    engine = AutoRunEngine()
    status = engine.get_status(comp_id)
    running = engine.is_running(comp_id)
    return {
        "running": running,
        "status": status,
    }


@router.get("/competitions/{comp_id}/stats")
async def get_competition_stats(comp_id: int, db: AsyncSession = Depends(get_db)):
    """获取比赛统计信息"""
    result = await db.execute(select(LabCompetition).where(LabCompetition.id == comp_id))
    comp = result.scalars().first()
    if not comp:
        raise HTTPException(status_code=404, detail="比赛不存在")

    # 参赛者统计
    pr = await db.execute(
        select(LabParticipant).where(LabParticipant.competition_id == comp_id)
    )
    participants = pr.scalars().all()

    total_trades = sum(p.total_trades for p in participants)
    avg_return = sum(p.total_return for p in participants) / max(len(participants), 1)
    best = max(participants, key=lambda p: p.total_return) if participants else None
    worst = min(participants, key=lambda p: p.total_return) if participants else None

    # 交易统计
    trade_count = 0
    buy_count = 0
    sell_count = 0
    for p in participants:
        tr = await db.execute(
            select(LabCompTrade).where(LabCompTrade.participant_id == p.id)
        )
        trades = tr.scalars().all()
        trade_count += len(trades)
        buy_count += sum(1 for t in trades if t.action == "buy")
        sell_count += sum(1 for t in trades if t.action == "sell")

    return {
        "competition": {
            "id": comp.id, "name": comp.name, "status": comp.status,
            "total_rounds": comp.total_rounds,
            "start_date": comp.start_date, "end_date": comp.end_date,
        },
        "participants": {
            "total": len(participants),
            "active": sum(1 for p in participants if p.status == "active"),
        },
        "trades": {
            "total": trade_count,
            "buy": buy_count,
            "sell": sell_count,
        },
        "performance": {
            "avg_return": round(avg_return * 100, 2),
            "best_player": {"name": best.name, "return": round(best.total_return * 100, 2)} if best else None,
            "worst_player": {"name": worst.name, "return": round(worst.total_return * 100, 2)} if worst else None,
        },
    }


@router.get("/participants/{participant_id}/trades")
async def get_trades(participant_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LabCompTrade)
        .where(LabCompTrade.participant_id == participant_id)
        .order_by(desc(LabCompTrade.created_at))
        .limit(200)
    )
    trades = result.scalars().all()

    return [{
        "id": t.id, "symbol": t.symbol, "name": t.name,
        "action": t.action, "quantity": t.quantity, "price": t.price,
        "amount": t.amount, "fee": t.fee, "reason": t.reason,
        "confidence": t.confidence,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in trades]


@router.get("/participants/{participant_id}/positions")
async def get_positions(participant_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LabCompPosition).where(
            LabCompPosition.participant_id == participant_id,
            LabCompPosition.quantity > 0
        )
    )
    return [{
        "id": p.id, "symbol": p.symbol, "name": p.name,
        "quantity": p.quantity, "avg_cost": p.avg_cost,
        "current_price": p.current_price, "unrealized_pnl": p.unrealized_pnl,
    } for p in result.scalars().all()]


# ==================== 群聊 ====================

@router.get("/competitions/{comp_id}/chat")
async def get_chat(comp_id: int, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LabChatMessage)
        .where(LabChatMessage.competition_id == comp_id)
        .order_by(desc(LabChatMessage.created_at))
        .limit(limit)
    )
    messages = result.scalars().all()
    messages.reverse()

    # 获取参与者信息
    pr = await db.execute(
        select(LabParticipant).where(LabParticipant.competition_id == comp_id)
    )
    p_map = {p.id: p for p in pr.scalars().all()}

    return [{
        "id": m.id,
        "participant_id": m.participant_id,
        "participant_name": p_map[m.participant_id].name if m.participant_id and m.participant_id in p_map else "系统",
        "participant_avatar": p_map[m.participant_id].avatar if m.participant_id and m.participant_id in p_map else "📢",
        "content": m.content,
        "message_type": m.message_type,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in messages]


class ChatMessage(BaseModel):
    content: str

@router.post("/competitions/{comp_id}/chat")
async def post_chat(comp_id: int, data: ChatMessage, db: AsyncSession = Depends(get_db)):
    """用户发送群聊消息"""
    msg = LabChatMessage(
        competition_id=comp_id,
        participant_id=None,
        content=data.content,
        message_type="text",
    )
    db.add(msg)
    await db.commit()
    return {"message": "发送成功"}


# ==================== 排行榜 ====================

@router.get("/competitions/{comp_id}/leaderboard")
async def get_leaderboard(comp_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LabParticipant).where(
            LabParticipant.competition_id == comp_id,
            LabParticipant.status == "active"
        ).order_by(desc(LabParticipant.total_return))
    )
    participants = result.scalars().all()

    return [{
        "rank": i + 1,
        "id": p.id, "name": p.name, "avatar": p.avatar,
        "provider": p.provider, "model_name": p.model_name,
        "api_base": p.api_base, "system_prompt": p.system_prompt,
        "current_capital": p.current_capital,
        "total_return": p.total_return,
        "total_trades": p.total_trades,
        "win_rate": p.win_rate,
        "max_drawdown": p.max_drawdown,
    } for i, p in enumerate(participants)]


@router.get("/competitions/{comp_id}/equity-curve")
async def get_equity_curve(comp_id: int, db: AsyncSession = Depends(get_db)):
    """获取所有参赛者的收益曲线数据"""
    result = await db.execute(
        select(LabParticipant).where(
            LabParticipant.competition_id == comp_id,
            LabParticipant.status == "active"
        )
    )
    participants = result.scalars().all()

    curves = []
    for p in participants:
        # 获取该参赛者的所有交易记录,按时间排序
        tr = await db.execute(
            select(LabCompTrade)
            .where(LabCompTrade.participant_id == p.id)
            .order_by(LabCompTrade.created_at)
        )
        trades = tr.scalars().all()

        # 构建收益曲线: 从初始资金开始,每笔交易后计算总资产
        equity = [{"time": p.created_at.isoformat() if p.created_at else "", "value": p.initial_capital}]
        running_capital = p.initial_capital

        # 获取持仓
        pos_r = await db.execute(
            select(LabCompPosition).where(
                LabCompPosition.participant_id == p.id,
                LabCompPosition.quantity > 0
            )
        )
        positions = {pos.symbol: pos for pos in pos_r.scalars().all()}

        for t in trades:
            if t.action == "buy":
                running_capital -= t.amount + t.fee
            else:
                running_capital += t.amount - t.fee
            equity.append({
                "time": t.created_at.isoformat() if t.created_at else "",
                "value": running_capital,
            })

        # 加上当前持仓市值
        market_value = sum(pos.current_price * pos.quantity for pos in positions.values())
        total = running_capital + market_value
        equity.append({
            "time": shanghai_now().isoformat(),
            "value": total,
        })

        curves.append({
            "participant_id": p.id,
            "name": p.name,
            "avatar": p.avatar,
            "color": _get_color(p.id),
            "equity": equity,
        })

    return curves


def _get_color(pid: int) -> str:
    """为每个参赛者分配颜色"""
    colors = ["#ef232a", "#409eff", "#67c23a", "#e6a23c", "#f56c6c", "#909399", "#b37feb", "#36cfc9"]
    return colors[(pid - 1) % len(colors)]


# ==================== 事件时间线 ====================

@router.get("/competitions/{comp_id}/events")
async def get_events(comp_id: int, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """获取比赛事件时间线"""
    from app.models.laboratory import LabCompEvent
    result = await db.execute(
        select(LabCompEvent)
        .where(LabCompEvent.competition_id == comp_id)
        .order_by(LabCompEvent.created_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    events.reverse()

    # 获取参与者信息
    pr = await db.execute(
        select(LabParticipant).where(LabParticipant.competition_id == comp_id)
    )
    p_map = {p.id: p for p in pr.scalars().all()}

    return [{
        "id": e.id,
        "type": e.event_type,
        "title": e.title,
        "detail": e.detail,
        "participant": {
            "name": p_map[e.participant_id].name,
            "avatar": p_map[e.participant_id].avatar,
        } if e.participant_id and e.participant_id in p_map else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in events]


# ==================== 分析师管理 ====================

@router.get("/analysts")
async def get_analysts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LabAnalyst).order_by(LabAnalyst.sort_order)
    )
    return [{
        "id": a.id, "name": a.name, "role": a.role, "avatar": a.avatar,
        "provider": a.provider, "model_name": a.model_name,
        "is_active": a.is_active, "sort_order": a.sort_order,
    } for a in result.scalars().all()]


@router.post("/analysts")
async def create_analyst(data: AnalystCreate, db: AsyncSession = Depends(get_db)):
    a = LabAnalyst(
        name=data.name, role=data.role, avatar=data.avatar,
        system_prompt=data.system_prompt, provider=data.provider,
        api_base=data.api_base, api_key=data.api_key,
        model_name=data.model_name, sort_order=data.sort_order,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return {"id": a.id, "message": "创建成功"}


@router.put("/analysts/{analyst_id}")
async def update_analyst(analyst_id: int, data: AnalystCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LabAnalyst).where(LabAnalyst.id == analyst_id))
    a = result.scalars().first()
    if not a:
        raise HTTPException(status_code=404, detail="分析师不存在")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    await db.commit()
    return {"message": "更新成功"}


@router.delete("/analysts/{analyst_id}")
async def delete_analyst(analyst_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(LabAnalyst).where(LabAnalyst.id == analyst_id))
    await db.commit()
    return {"message": "已删除"}


# ==================== 研究任务 ====================

@router.get("/research")
async def get_research_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LabResearchTask).order_by(desc(LabResearchTask.created_at))
    )
    return [{
        "id": t.id, "symbol": t.symbol, "stock_name": t.stock_name,
        "status": t.status, "stage": t.stage, "progress": t.progress,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    } for t in result.scalars().all()]


@router.post("/research")
async def create_research_task(data: ResearchTaskCreate, db: AsyncSession = Depends(get_db)):
    task = LabResearchTask(
        symbol=data.symbol,
        stock_name=data.stock_name,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return {"id": task.id, "message": "研究任务已创建"}


@router.get("/research/{task_id}")
async def get_research_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LabResearchTask).where(LabResearchTask.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 分析师报告
    rr = await db.execute(
        select(LabAnalystReport).where(LabAnalystReport.task_id == task_id)
        .order_by(LabAnalystReport.created_at)
    )
    reports = rr.scalars().all()

    # 获取分析师信息
    ar = await db.execute(select(LabAnalyst))
    a_map = {a.id: a for a in ar.scalars().all()}

    # 最终报告
    fr = await db.execute(
        select(LabResearchReport).where(LabResearchReport.task_id == task_id)
    )
    final = fr.scalars().first()

    return {
        "id": task.id, "symbol": task.symbol, "stock_name": task.stock_name,
        "status": task.status, "stage": task.stage, "progress": task.progress,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "analyst_reports": [{
            "id": r.id,
            "analyst_name": a_map.get(r.analyst_id, None) and a_map[r.analyst_id].name or "未知",
            "analyst_role": a_map.get(r.analyst_id, None) and a_map[r.analyst_id].role or "",
            "stage": r.stage,
            "content": r.content,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in reports],
        "final_report": {
            "fundamental_score": final.fundamental_score,
            "technical_score": final.technical_score,
            "sentiment_score": final.sentiment_score,
            "overall_score": final.overall_score,
            "recommendation": final.recommendation,
            "target_price_low": final.target_price_low,
            "target_price_high": final.target_price_high,
            "risk_factors": final.risk_factors,
            "consensus": final.consensus,
            "divergences": final.divergences,
            "full_report": final.full_report,
        } if final else None,
    }


@router.post("/research/{task_id}/run")
async def run_research(task_id: int, db: AsyncSession = Depends(get_db)):
    """执行研究任务"""
    engine = ResearchTeamEngine(db)
    result = await engine.run_research(task_id)
    return result


@router.delete("/research/{task_id}")
async def delete_research(task_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(LabAnalystReport).where(LabAnalystReport.task_id == task_id))
    await db.execute(delete(LabResearchReport).where(LabResearchReport.task_id == task_id))
    await db.execute(delete(LabResearchTask).where(LabResearchTask.id == task_id))
    await db.commit()
    return {"message": "已删除"}
