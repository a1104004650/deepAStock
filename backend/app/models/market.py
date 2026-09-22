from datetime import datetime, date, time
from decimal import Decimal
from sqlalchemy import String, Integer, BigInteger, DateTime, Date, Time, Numeric, JSON, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.utils import shanghai_now


class Kline(Base):
    __tablename__ = "klines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=True)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=True)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=True)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=True)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    turnover: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())

    __table_args__ = (UniqueConstraint("symbol", "period", "timestamp", name="uq_kline_sp_t"),)


class MoneyFlow(Base):
    __tablename__ = "money_flow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    main_net: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    retail_net: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    big_net: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    mid_net: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    small_net: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)


class SectorMoneyFlow(Base):
    __tablename__ = "sector_money_flow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sector_code: Mapped[str] = mapped_column(String(20), nullable=False)
    sector_name: Mapped[str] = mapped_column(String(50), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    net_inflow: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    outflow: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    leader_symbol: Mapped[str] = mapped_column(String(20), nullable=True)


class DragonTiger(Base):
    __tablename__ = "dragon_tiger"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_dt_symbol_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=True)
    buy_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    sell_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    buyer_list = mapped_column(JSON, default=list)
    seller_list = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class LimitUp(Base):
    __tablename__ = "limit_up"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=True)
    high_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=True)
    close_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=True)
    limit_time: Mapped[time] = mapped_column(Time, nullable=True)
    first_limit: Mapped[bool] = mapped_column(Boolean, default=False)
    consecutive_days: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    circulation: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    sector: Mapped[str] = mapped_column(String(50), nullable=True)


class StockName(Base):
    """A股全量股票代码-名称本地库（每月刷新）"""
    __tablename__ = "stock_names"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class ReplayReport(Base):
    __tablename__ = "replay_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    market_summary = mapped_column(JSON, default=dict)
    sector_flow = mapped_column(JSON, default=list)
    limit_analysis = mapped_column(JSON, default=dict)
    stock_pool = mapped_column(JSON, default=list)
    agent_reviews = mapped_column(JSON, default=dict)
    report_md: Mapped[str] = mapped_column(Text, nullable=True)
    report_html: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())
