from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.utils import shanghai_now


class StrategyConfig(Base):
    """回测策略配置（内置 + 用户自定义）。params_schema 驱动前端表单，code 为 run(bars, params) 实现。"""
    __tablename__ = "strategy_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    params_schema = mapped_column(JSON, default=list)
    code: Mapped[str] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now(), onupdate=lambda: shanghai_now())