"""FastAPI application for the paper trading terminal."""

from __future__ import annotations

from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from quantit.api.frontend import mount_frontend
from quantit.api.schemas import (
    AccountOut,
    BarOut,
    InstrumentOut,
    MarketOut,
    NoteIn,
    NoteOut,
    OrderIn,
    OrderOut,
    PositionOut,
    QuoteOut,
    SignalBundleOut,
    StrategyOut,
    TradeOut,
)
from quantit.markets.registry import MarketRegistry, get_registry
from quantit.paper.broker import PaperBroker
from quantit.paper.db import create_session, session_on
from quantit.paper.notes import NoteBook
from quantit.strategy.catalog import get_strategy, list_strategies
from quantit.strategy.signals import evaluate_signals


def _bar_time(index_value, interval: str) -> str:
    ts = pd.Timestamp(index_value)
    if interval == "1d":
        return ts.strftime("%Y-%m-%d")
    return ts.isoformat()


def _order_out(order) -> OrderOut:
    return OrderOut(
        id=order.id,
        market_id=order.market_id,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        status=order.status,
        fill_price=order.fill_price,
        commission=order.commission,
        reject_reason=order.reject_reason,
        rationale=order.rationale,
        created_at=order.created_at,
        fill_time=order.fill_time,
    )


def create_app(
    broker: PaperBroker | None = None,
    registry: MarketRegistry | None = None,
    notebook: NoteBook | None = None,
) -> FastAPI:
    registry = registry or get_registry()
    if broker is None:
        broker = PaperBroker(create_session(), registry=registry)
    broker.ensure_accounts()
    notebook = notebook or NoteBook(session_on(broker.session.get_bind()), now=broker.now)

    app = FastAPI(title="QuantiT Paper Terminal", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.broker = broker
    app.state.registry = registry
    app.state.notebook = notebook

    def _adapter(market_id: str):
        try:
            return registry.get(market_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/markets", response_model=List[MarketOut])
    def list_markets() -> List[MarketOut]:
        return [
            MarketOut(
                id=adapter.market_id,
                name=adapter.profile.name,
                currency=adapter.profile.currency,
                timezone=adapter.timezone,
                session_hours=adapter.session_hours,
                t_plus=adapter.t_plus,
                intervals=list(adapter.supported_intervals),
            )
            for adapter in registry.all()
        ]

    @app.get("/api/v1/search", response_model=List[InstrumentOut])
    def search(market: str, q: str = "") -> List[InstrumentOut]:
        adapter = _adapter(market)
        return [InstrumentOut(**inst.__dict__) for inst in adapter.search(q)]

    @app.get("/api/v1/instrument", response_model=InstrumentOut)
    def instrument(market: str, symbol: str) -> InstrumentOut:
        adapter = _adapter(market)
        inst = adapter.instrument(symbol)
        return InstrumentOut(**inst.__dict__)

    @app.get("/api/v1/quote", response_model=QuoteOut)
    def quote(market: str, symbol: str) -> QuoteOut:
        adapter = _adapter(market)
        try:
            q = adapter.fetch_quote(symbol)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return QuoteOut(**q.__dict__)

    @app.get("/api/v1/bars", response_model=List[BarOut])
    def bars(
        market: str,
        symbol: str,
        interval: str = "1d",
        start: str = Query(default=""),
        end: str = Query(default=""),
    ) -> List[BarOut]:
        adapter = _adapter(market)
        end_ts = pd.Timestamp(end) if end else pd.Timestamp.utcnow()
        start_ts = pd.Timestamp(start) if start else end_ts - pd.Timedelta(days=365)
        try:
            df = adapter.fetch_bars(symbol, interval, start_ts, end_ts)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        out: List[BarOut] = []
        for idx, row in df.iterrows():
            out.append(
                BarOut(
                    time=_bar_time(idx, interval),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return out

    @app.get("/api/v1/strategies", response_model=List[StrategyOut])
    def strategies(market: Optional[str] = None) -> List[StrategyOut]:
        return [StrategyOut(**row) for row in list_strategies(market)]

    @app.get("/api/v1/strategies/{strategy_id}", response_model=StrategyOut)
    def strategy_detail(strategy_id: str) -> StrategyOut:
        row = get_strategy(strategy_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown strategy: {strategy_id}")
        return StrategyOut(**row)

    @app.get("/api/v1/signals", response_model=SignalBundleOut)
    def signals(market: str, symbol: str) -> SignalBundleOut:
        adapter = _adapter(market)
        canonical = adapter.normalize_symbol(symbol)
        end_ts = pd.Timestamp.utcnow()
        start_ts = end_ts - pd.Timedelta(days=365)
        try:
            df = adapter.fetch_bars(canonical, "1d", start_ts, end_ts)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        bundle = evaluate_signals(market, canonical, df)
        return SignalBundleOut(**bundle)

    @app.get("/api/v1/notes", response_model=List[NoteOut])
    def list_notes(market: Optional[str] = None, symbol: Optional[str] = None) -> List[NoteOut]:
        rows = notebook.list_notes(market_id=market, symbol=symbol)
        return [
            NoteOut(
                id=n.id,
                body=n.body,
                market_id=n.market_id,
                symbol=n.symbol,
                created_at=n.created_at,
            )
            for n in rows
        ]

    @app.post("/api/v1/notes", response_model=NoteOut)
    def create_note(body: NoteIn) -> NoteOut:
        try:
            note = notebook.add_note(body.body, market_id=body.market_id, symbol=body.symbol)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return NoteOut(
            id=note.id,
            body=note.body,
            market_id=note.market_id,
            symbol=note.symbol,
            created_at=note.created_at,
        )

    @app.delete("/api/v1/notes/{note_id}")
    def delete_note(note_id: int) -> dict:
        try:
            notebook.delete_note(note_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True}

    @app.get("/api/v1/accounts", response_model=List[AccountOut])
    def accounts() -> List[AccountOut]:
        return [
            AccountOut(
                market_id=a.market_id,
                currency=a.currency,
                cash=a.cash,
                initial_cash=a.initial_cash,
            )
            for a in broker.list_accounts()
        ]

    @app.get("/api/v1/orders", response_model=List[OrderOut])
    def orders(market: Optional[str] = None) -> List[OrderOut]:
        return [_order_out(o) for o in broker.list_orders(market)]

    @app.get("/api/v1/trades", response_model=List[TradeOut])
    def trades(market: Optional[str] = None) -> List[TradeOut]:
        return [
            TradeOut(
                id=t.id,
                order_id=t.order_id,
                market_id=t.market_id,
                symbol=t.symbol,
                side=t.side,
                quantity=t.quantity,
                price=t.price,
                commission=t.commission,
                timestamp=t.timestamp,
            )
            for t in broker.list_trades(market)
        ]

    @app.get("/api/v1/positions", response_model=List[PositionOut])
    def positions(market: Optional[str] = None) -> List[PositionOut]:
        return [
            PositionOut(
                market_id=p.market_id,
                symbol=p.symbol,
                quantity=p.quantity,
                avg_cost=p.avg_cost,
            )
            for p in broker.list_positions(market)
        ]

    @app.post("/api/v1/orders", response_model=OrderOut)
    def place_order(body: OrderIn) -> OrderOut:
        _adapter(body.market)
        try:
            order = broker.place_order(
                body.market,
                body.symbol,
                body.side,
                body.quantity,
                rationale=body.rationale,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _order_out(order)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    mount_frontend(app)
    return app


app = None


def get_app() -> FastAPI:
    global app
    if app is None:
        app = create_app()
    return app
