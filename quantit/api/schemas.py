"""Pydantic schemas for the paper terminal API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field

NOTE_MAX_LEN = 4000


class MarketOut(BaseModel):
    id: str
    name: str
    currency: str
    timezone: str
    session_hours: str
    t_plus: int
    intervals: List[str]
    allowed_asset_classes: List[str] = Field(default_factory=list)


class InstrumentOut(BaseModel):
    symbol: str
    market_id: str
    name: str
    currency: str
    lot_size: int
    timezone: str
    session_hours: str
    asset_class: str = "equity"
    multiplier: int = 1


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
    rationale: Optional[str] = None


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
    rationale: Optional[str] = None
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


class StrategyParamOut(BaseModel):
    name: str
    value: Any
    type: str
    description: str = ""


class StrategyMemberOut(BaseModel):
    symbol: str
    name: str


class StrategyOut(BaseModel):
    id: str
    name: str
    class_name: str
    markets: List[str]
    horizon: str
    summary: str
    thesis: str
    rules: List[str]
    parameters: List[StrategyParamOut]
    universe: Optional[dict] = None
    score_weights: Optional[dict] = None


class SignalOut(BaseModel):
    strategy_id: str
    name: str
    action: str
    reason: str
    values: dict = Field(default_factory=dict)


class SignalBundleOut(BaseModel):
    market_id: str
    symbol: str
    asof: Optional[str] = None
    headline: str
    signals: List[SignalOut]
    evaluated_at: str


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=NOTE_MAX_LEN)
    market_id: Optional[str] = None
    symbol: Optional[str] = None


class NoteOut(BaseModel):
    id: int
    body: str
    market_id: Optional[str] = None
    symbol: Optional[str] = None
    created_at: datetime


class RunnerActionOut(BaseModel):
    time: Optional[str] = None
    market_id: str
    symbol: str
    side: str
    quantity: int
    status: str
    rationale: Optional[str] = None
    reject_reason: Optional[str] = None


class RunnerOut(BaseModel):
    running: bool
    interval_sec: int
    last_tick: Optional[str] = None
    last_error: Optional[str] = None
    seed_cash: dict
    cash: dict
    allowed: dict
    watchlists: dict
    actions: List[RunnerActionOut]
