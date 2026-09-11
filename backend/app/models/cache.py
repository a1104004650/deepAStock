from datetime import datetime, date
from sqlalchemy import String, Integer, DateTime, Date
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class CacheMetadata(Base):
    """数据缓存元数据 - 避免重复请求历史数据"""
    __tablename__ = "cache_metadata"

    data_type: Mapped[str] = mapped_column(String(50), primary_key=True)  # kline/financial/dragon_tiger
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    period: Mapped[str] = mapped_column(String(10), primary_key=True, default="")
    last_date: Mapped[date] = mapped_column(Date, nullable=True)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(20), default="ok")
