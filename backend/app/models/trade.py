from datetime import datetime, date, time
from decimal import Decimal
from sqlalchemy import String, Integer, DateTime, Date, Time, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.utils import shanghai_now


class UserTrade(Base):
    __tablename__ = "user_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # buy/sell
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    trade_time: Mapped[time] = mapped_column(Time, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    imported_from: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class UserPosition(Base):
    __tablename__ = "user_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=True)
    total_buy_qty: Mapped[int] = mapped_column(Integer, default=0)
    total_sell_qty: Mapped[int] = mapped_column(Integer, default=0)
    remaining_qty: Mapped[int] = mapped_column(Integer, default=0)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    total_return: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    return_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now(), onupdate=lambda: shanghai_now())
