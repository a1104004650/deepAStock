"""智能体执行器 - 编排各类任务"""
import time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.agent.base import AgentContext, AgentResult
from app.core.agent.registry import create_agent, get_agent_configs, DEFAULT_AGENTS
from app.models.agent import AgentConfig, AgentRun
from app.utils.logger import logger


class AgentExecutor:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_config(self, agent_config_id: int = None, agent_type: str = None) -> dict:
        if agent_config_id:
            row = (await self.db.execute(select(AgentConfig).where(AgentConfig.id == agent_config_id))).scalars().first()
            if row:
                return {"id": row.id, "agent_type": row.agent_type, "name": row.name,
                        "system_prompt": row.system_prompt, "model_name": row.model_name,
                        "api_base": row.api_base, "api_key": row.api_key,
                        "temperature": row.temperature, "max_tokens": row.max_tokens}
        # 按类型找默认
        rows = await get_agent_configs(self.db)
        for r in rows:
            if r.get("agent_type") == agent_type:
                return r
        for a in DEFAULT_AGENTS:
            if a["agent_type"] == agent_type:
                return a
        # 未知类型兜底到 research，避免配置错误导致接口 500
        logger.warning(f"unknown agent_type {agent_type}, fallback to research")
        for a in DEFAULT_AGENTS:
            if a["agent_type"] == "research":
                return a
        raise ValueError(f"unknown agent_type: {agent_type}")

    async def run(self, agent_type: str = None, agent_config_id: int = None,
                  task: str = "analyze_stock", context: AgentContext = None) -> AgentResult:
        config = await self._load_config(agent_config_id, agent_type)
        agent = create_agent(config)
        ctx = context or AgentContext()
        handler = getattr(agent, task, None)
        if handler is None:
            raise ValueError(f"unsupported task: {task}")

        start = time.time()
        result_cfg_id = config.get("id") or -1
        try:
            result: AgentResult = await handler(ctx)
            await self._record_run(result_cfg_id, task, ctx, result, "success", start)
            return result
        except Exception as e:
            logger.error(f"agent run failed: {e}")
            await self._record_run(result_cfg_id, task, ctx, None, "failed", start, str(e))
            return AgentResult(agent_type=agent_type, summary=f"运行失败: {e}", reasoning=str(e), confidence=0.0)

    async def _record_run(self, config_id: int, task: str, ctx: AgentContext,
                          result: AgentResult, status: str, start: float, err: str = None):
        try:
            run = AgentRun(
                agent_config_id=config_id if config_id > 0 else None,
                task_type=task,
                input_data=ctx.model_dump(mode="json") if hasattr(ctx, "model_dump") else {},
                output_data=result.model_dump() if result else {},
                status=status,
                error_message=err,
                duration_ms=int((time.time() - start) * 1000),
            )
            self.db.add(run)
            await self.db.commit()
        except Exception as e:
            logger.warning(f"record run failed: {e}")
            await self.db.rollback()