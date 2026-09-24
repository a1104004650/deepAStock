"""智能体注册与工厂"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.agent.base import BaseAgent
from app.core.agent.research_agent import ResearchAgent, PROMPT_RESEARCH
from app.core.agent.short_term_agent import ShortTermAgent, PROMPT_SHORT_TERM
from app.core.agent.swing_agent import SwingAgent, PROMPT_SWING
from app.models.agent import AgentConfig
from app.config import settings

AGENT_CLASSES = {
    "research": ResearchAgent,
    "short_term": ShortTermAgent,
    "swing": SwingAgent,
}

LLM_API_BASE = settings.LLM_API_BASE
LLM_MODEL = settings.LLM_MODEL
LLM_API_KEY = settings.LLM_API_KEY

DEFAULT_AGENTS = [
    {
        "agent_type": "research", "name": "投研智能体", "is_default": True,
        "system_prompt": PROMPT_RESEARCH,
        "model_name": LLM_MODEL, "api_base": LLM_API_BASE, "api_key": LLM_API_KEY,
        "max_tokens": 4000, "temperature": 0.3,
    },
    {
        "agent_type": "short_term", "name": "短线大师", "is_default": True,
        "system_prompt": PROMPT_SHORT_TERM,
        "model_name": LLM_MODEL, "api_base": LLM_API_BASE, "api_key": LLM_API_KEY,
        "max_tokens": 4000, "temperature": 0.2,
    },
    {
        "agent_type": "swing", "name": "波段助手", "is_default": True,
        "system_prompt": PROMPT_SWING,
        "model_name": LLM_MODEL, "api_base": LLM_API_BASE, "api_key": LLM_API_KEY,
        "max_tokens": 4000, "temperature": 0.3,
    },
]


def create_agent(config: dict) -> BaseAgent:
    """根据配置创建智能体实例"""
    agent_type = config.get("agent_type", "custom")
    cls = AGENT_CLASSES.get(agent_type)
    if cls is None:
        # 自定义智能体用基类（模拟）
        class CustomAgent(BaseAgent):
            agent_type = "custom"
            default_prompt = config.get("system_prompt") or "你是一个股票分析智能体。"

            async def analyze_stock(self, ctx):
                return await self._predict(ctx, f"请分析 {ctx.symbol}。数据:{self._compact(ctx.market_data)}")

            async def daily_replay(self, ctx):
                return await self._predict(ctx, f"请复盘 {ctx.date}。数据:{self._compact(ctx.market_data)}")

            async def select_pool(self, ctx):
                return await self._predict(ctx, f"请生成选股池。数据:{self._compact(ctx.market_data)}")

        return CustomAgent(config)
    return cls(config)


async def get_agent_configs(db: AsyncSession, user_id: int = 0, expose_secrets: bool = True) -> list[dict]:
    rows = (await db.execute(
        select(AgentConfig).where(AgentConfig.user_id.in_([user_id, 0]))
        .order_by(AgentConfig.id)
    )).scalars().all()
    result = [{
        "id": r.id, "agent_type": r.agent_type, "name": r.name, "system_prompt": r.system_prompt,
        "model_name": r.model_name, "api_base": r.api_base,
        "api_key": r.api_key if expose_secrets else None,
        "has_api_key": bool(r.api_key),
        "provider": getattr(r, "provider", None),
        "temperature": float(r.temperature), "max_tokens": r.max_tokens,
        "is_active": r.is_active, "is_default": r.is_default,
    } for r in rows]
    # 若无配置，返回默认三个
    if not any(r.get("is_default") for r in result):
        result = [default_agent_to_dict(a, 0) for a in DEFAULT_AGENTS]
        if not expose_secrets:
            for row in result:
                row["has_api_key"] = bool(row.get("api_key"))
                row["api_key"] = None
    return result


def default_agent_to_dict(a: dict, user_id: int = 0) -> dict:
    d = dict(a)
    d["user_id"] = user_id
    d.setdefault("api_base", LLM_API_BASE)
    d.setdefault("api_key", LLM_API_KEY)
    d.setdefault("model_name", LLM_MODEL)
    return d


async def ensure_default_agents(db: AsyncSession) -> None:
    """确保默认三个智能体存在，并幂等补齐默认模型配置（amd DeepSeek）"""
    for a in DEFAULT_AGENTS:
        res = await db.execute(select(AgentConfig).where(
            AgentConfig.agent_type == a["agent_type"],
            AgentConfig.is_default == True))  # noqa: E712
        row = res.scalars().first()
        fields = {"name": a["name"], "system_prompt": a["system_prompt"],
                  "model_name": a["model_name"],
                  "max_tokens": a["max_tokens"], "temperature": a["temperature"],
                  "is_default": True, "user_id": 0}
        if row is None:
            db.add(AgentConfig(**{**a, "user_id": 0}))
        else:
            # 仅当用户未自定义过密钥时才覆盖模型配置，避免覆盖用户的改动
            need_creds = not (row.api_key or row.api_base)
            for k, v in fields.items():
                setattr(row, k, v)
            if need_creds:
                row.api_base = a["api_base"]
                row.api_key = a["api_key"]
    await db.commit()
