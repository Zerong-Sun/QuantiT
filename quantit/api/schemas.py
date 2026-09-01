"""Pydantic schemas for the paper terminal API."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MarketOut(BaseModel):
    id: str
    name: str
    currency: str
    timezone: str
    session_hours: str
    t_plus: int
    intervals: List[str]


class InstrumentOut(BaseModel):
    symbol: str
    market_id: str
    name: str
    currency: str
    lot_size: int
    timezone: str
    session_hours: str


class QuoteOut(BaseModel):
    symbol: str
    market_id: str
    last: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    prev_close: Optional[float] = None
    volume: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    timestamp: Optional[datetime] = None
    delayed: bool = True


class BarOut(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderIn(BaseModel):
    market: str
    symbol: str
    side: str
    quantity: int = Field(gt=0)


class OrderOut(BaseModel):
    id: int
    market_id: str
    symbol: str
    side: str
    quantity: int
    status: str
    fill_price: float
    commission: float
    reject_reason: Optional[str] = None
    created_at: datetime
    fill_time: Optional[datetime] = None


class TradeOut(BaseModel):
    id: int
    order_id: int
    market_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    commission: float
    timestamp: datetime


class PositionOut(BaseModel):
    market_id: str
    symbol: str
    quantity: int
    avg_cost: float


class AccountOut(BaseModel):
    market_id: str
    currency: str
    cash: float
    initial_cash: float
