from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Integer, BigInteger, DateTime, Date, Text, Numeric, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Stock(Base):
    __tablename__ = "stocks"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=True)
    list_date: Mapped[date] = mapped_column(Date, nullable=True)
    total_share: Mapped[int] = mapped_column(BigInteger, nullable=True)
    industry: Mapped[str] = mapped_column(String(50), nullable=True)
    concept_tags = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class FinancialQuarterly(Base):
    __tablename__ = "financial_quarterly"
    __table_args__ = (UniqueConstraint("symbol", "report_date", name="uq_fin_symbol_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), ForeignKey("stocks.symbol"), index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    revenue: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    revenue_yoy: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    net_profit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    net_profit_yoy: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    gross_margin: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    roe: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    eps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    bps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    ocf: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Shareholder(Base):
    __tablename__ = "shareholders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), ForeignKey("stocks.symbol"), index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    holder_name: Mapped[str] = mapped_column(String(100), nullable=True)
    hold_count: Mapped[int] = mapped_column(BigInteger, nullable=True)
    hold_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    change_count: Mapped[int] = mapped_column(BigInteger, nullable=True)
    is_major: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SentimentDaily(Base):
    __tablename__ = "sentiment_daily"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    news_count: Mapped[int] = mapped_column(Integer, nullable=True)
    positive_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=True)
    negative_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=True)
    attention_rank: Mapped[int] = mapped_column(Integer, nullable=True)
    forum_activity: Mapped[int] = mapped_column(Integer, nullable=True)


class Sector(Base):
    __tablename__ = "sectors"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=True)
    parent_code: Mapped[str] = mapped_column(String(20), nullable=True)
    stocks = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
