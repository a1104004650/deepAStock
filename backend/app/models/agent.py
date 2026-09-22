from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, DateTime, Text, Numeric, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.utils import shanghai_now


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    agent_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[int] = mapped_column(Integer, default=1)
    prompt_history = mapped_column(JSON, default=list)
    model_name: Mapped[str] = mapped_column(String(100), nullable=True, default="deepseek-chat")
    provider: Mapped[str] = mapped_column(String(20), nullable=True)
    api_base: Mapped[str] = mapped_column(String(500), nullable=True)
    api_key: Mapped[str] = mapped_column(String(500), nullable=True)
    temperature: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0.3)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4000)
    extra_params = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now(), onupdate=lambda: shanghai_now())


class AgentPromptLog(Base):
    __tablename__ = "agent_prompt_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_config_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_configs.id"), nullable=True)
    agent_type: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=True)
    performance_score = mapped_column(Numeric(4, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_config_id: Mapped[int] = mapped_column(Integer, index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="agent")  # agent/lab_competition/lab_research
    source_id: Mapped[int] = mapped_column(Integer, nullable=True)  # 参赛者ID或任务ID
    task_type: Mapped[str] = mapped_column(String(50), nullable=True)
    input_data = mapped_column(JSON, default=dict)
    output_data = mapped_column(JSON, default=dict)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    week_key: Mapped[str] = mapped_column(String(10), nullable=True, index=True)  # 2026-W38
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class StockAiAnalysis(Base):
    """AI 个股分析持久化：同一标的当日不重复调用，切换个股直接读缓存展示。"""
    __tablename__ = "stock_ai_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    payload = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())
