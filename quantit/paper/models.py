"""SQLAlchemy models for paper trading accounts, orders, and lots."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    currency: Mapped[str] = mapped_column(String(8))
    cash: Mapped[float] = mapped_column(Float)
    initial_cash: Mapped[float] = mapped_column(Float)

    positions: Mapped[list[Position]] = relationship(back_populates="account")
    orders: Mapped[list[Order]] = relationship(back_populates="account")
    trades: Mapped[list[Trade]] = relationship(back_populates="account")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    market_id: Mapped[str] = mapped_column(String(8), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0)

    account: Mapped[Account] = relationship(back_populates="positions")
    lots: Mapped[list[PositionLot]] = relationship(back_populates="position")


class PositionLot(Base):
    __tablename__ = "position_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    remaining: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    acquired_on: Mapped[datetime] = mapped_column(DateTime)

    position: Mapped[Position] = relationship(back_populates="lots")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    market_id: Mapped[str] = mapped_column(String(8), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    fill_price: Mapped[float] = mapped_column(Float, default=0.0)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    fill_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    account: Mapped[Account] = relationship(back_populates="orders")
    trades: Mapped[list[Trade]] = relationship(back_populates="order")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    market_id: Mapped[str] = mapped_column(String(8), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime)

    order: Mapped[Order] = relationship(back_populates="trades")
    account: Mapped[Account] = relationship(back_populates="trades")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    market_id: Mapped[Optional[str]] = mapped_column(String(8), nullable=True, index=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
