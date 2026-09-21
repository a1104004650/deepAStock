"""实验室AI调用记录工具"""
import time
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.agent import AgentRun


def get_week_key(dt: datetime = None) -> str:
    """获取ISO周标识，如 2026-W38"""
    dt = dt or datetime.utcnow()
    return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"


async def record_lab_call(
    db: AsyncSession,
    source: str,          # lab_competition / lab_research
    source_id: int,       # 参赛者ID或任务ID
    task_type: str,       # trading_decision / analyst_research / cross_discuss / final_report
    provider: str,
    model_name: str,
    prompt: str = "",
    result: dict = None,
    status: str = "success",
    error: str = None,
    duration_ms: int = 0,
    tokens_used: int = None,
):
    """记录一次实验室AI调用"""
    run = AgentRun(
        source=source,
        source_id=source_id,
        task_type=task_type,
        input_data={"provider": provider, "model": model_name, "prompt_preview": prompt[:500] if prompt else ""},
        output_data=result or {},
        tokens_used=tokens_used,
        status=status,
        error_message=error,
        duration_ms=duration_ms,
        week_key=get_week_key(),
    )
    db.add(run)
    return run


async def get_weekly_stats(db: AsyncSession, week_key: str = None):
    """获取指定周的AI调用统计"""
    week_key = week_key or get_week_key()

    result = await db.execute(
        select(AgentRun).where(AgentRun.week_key == week_key)
        .order_by(AgentRun.created_at.desc())
    )
    runs = result.scalars().all()

    # 按来源分组
    by_source = {}
    for r in runs:
        src = r.source or "agent"
        if src not in by_source:
            by_source[src] = {"total": 0, "success": 0, "failed": 0, "total_ms": 0}
        by_source[src]["total"] += 1
        if r.status == "success":
            by_source[src]["success"] += 1
        else:
            by_source[src]["failed"] += 1
        by_source[src]["total_ms"] += r.duration_ms or 0

    # 按任务类型分组
    by_task = {}
    for r in runs:
        tt = r.task_type or "unknown"
        if tt not in by_task:
            by_task[tt] = 0
        by_task[tt] += 1

    return {
        "week_key": week_key,
        "total_calls": len(runs),
        "by_source": by_source,
        "by_task": by_task,
        "recent_runs": [{
            "id": r.id,
            "source": r.source,
            "source_id": r.source_id,
            "task_type": r.task_type,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in runs[:50]],
    }
