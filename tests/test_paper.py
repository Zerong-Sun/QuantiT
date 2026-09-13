"""Tests for the persisted paper broker (no network)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from quantit.data.provider import DataProvider
from quantit.markets.cn import CNAdapter
from quantit.markets.hk import HKAdapter
from quantit.markets.registry import MarketRegistry
from quantit.markets.us import USAdapter
from quantit.paper.broker import PaperBroker
from quantit.paper.db import create_session, purge_zero_quantity_positions
from quantit.paper.models import Account, Order, Position, PositionLot


def _ohlcv(n: int = 3, start: str = "2024-06-03", start_price: float = 100.0) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    prices = [start_price + i for i in range(n)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [1_000_000.0] * n,
        },
        index=dates,
    )


class FakeProvider(DataProvider):
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def fetch(self, symbol, start, end, interval: str = "1d") -> pd.DataFrame:
        if symbol not in self.frames:
            raise ValueError(f"No data returned for {symbol}")
        return self.frames[symbol].copy()


def _registry() -> MarketRegistry:
    registry = MarketRegistry()
    registry.register(USAdapter(provider=FakeProvider({"AAPL": _ohlcv(start_price=100.0)})))
    registry.register(HKAdapter(provider=FakeProvider({"0700.HK": _ohlcv(start_price=300.0)})))
    registry.register(CNAdapter(provider=FakeProvider({"600519.SS": _ohlcv(start_price=10.0)})))
    return registry


@pytest.fixture
def broker() -> PaperBroker:
    session = create_session("sqlite:///:memory:")
    clock = {"now": datetime(2024, 6, 10, 10, 0, 0)}
    paper = PaperBroker(
        session,
        registry=_registry(),
        now=lambda: clock["now"],
    )
    paper.ensure_accounts(cash=100_000.0)
    paper.clock = clock
    return paper


class TestAccounts:
    def test_seeds_three_currency_accounts(self, broker: PaperBroker) -> None:
        accounts = {a.market_id: a for a in broker.list_accounts()}
        assert set(accounts) == {"us", "us_book", "hk", "hk_theme", "cn", "cn_etf"}
        assert accounts["us"].currency == "USD"
        assert accounts["us_book"].currency == "USD"
        assert accounts["hk"].currency == "HKD"
        assert accounts["hk_theme"].currency == "HKD"
        assert accounts["cn"].currency == "CNY"
        assert accounts["cn_etf"].currency == "CNY"
        assert accounts["us"].cash == 100_000.0
        assert accounts["us_book"].cash == 100_000.0


class TestMarketOrder:
    def test_buy_fills_at_quote_plus_slippage(self, broker: PaperBroker) -> None:
        order = broker.place_order("us", "AAPL", "buy", 10)
        assert order.status == "filled"
        # last close is 102, slippage 0.05%
        assert order.fill_price == pytest.approx(102.0 * 1.0005)
        pos = broker.get_position("us", "AAPL")
        assert pos is not None
        assert pos.quantity == 10
        trades = broker.list_trades("us")
        assert len(trades) == 1
        assert trades[0].side == "buy"

    def test_reads_during_quote_fetch_do_not_poison_session(self, broker: PaperBroker) -> None:
        import threading

        adapter = broker.adapter_for("us")
        orig = adapter.fetch_quote
        entered = threading.Event()
        release = threading.Event()

        def blocked(symbol: str):
            entered.set()
            assert release.wait(2.0)
            return orig(symbol)

        adapter.fetch_quote = blocked  # type: ignore[method-assign]
        errors: list[BaseException] = []
        filled: list = []

        def buy() -> None:
            try:
                filled.append(broker.place_order("us", "AAPL", "buy", 10))
            except BaseException as exc:  # noqa: BLE001 — capture for the parent thread
                errors.append(exc)

        worker = threading.Thread(target=buy)
        worker.start()
        assert entered.wait(2.0)
        accounts = broker.list_accounts()
        assert accounts
        release.set()
        worker.join(3.0)
        assert not worker.is_alive()
        assert errors == []
        assert filled and filled[0].status == "filled"

    def test_rejects_sell_when_flat(self, broker: PaperBroker) -> None:
        order = broker.place_order("us", "AAPL", "sell", 1)
        assert order.status == "rejected"
        assert "short" in (order.reject_reason or "").lower() or "insufficient" in (
            order.reject_reason or ""
        ).lower()

    def test_rejects_without_quote(self, broker: PaperBroker) -> None:
        order = broker.place_order("us", "MSFT", "buy", 1)
        assert order.status == "rejected"
        assert "quote" in (order.reject_reason or "").lower()

    def test_rejects_insufficient_cash(self, broker: PaperBroker) -> None:
        order = broker.place_order("us", "AAPL", "buy", 10_000)
        assert order.status == "rejected"
        assert "cash" in (order.reject_reason or "").lower()


class TestVenueRules:
    def test_cn_rejects_non_board_lot(self, broker: PaperBroker) -> None:
        order = broker.place_order("cn", "600519", "buy", 150)
        assert order.status == "rejected"
        assert "100" in (order.reject_reason or "")

    def test_cn_t_plus_one_blocks_same_day_sell(self, broker: PaperBroker) -> None:
        buy = broker.place_order("cn", "600519", "buy", 100)
        assert buy.status == "filled"
        sell = broker.place_order("cn", "600519", "sell", 100)
        assert sell.status == "rejected"
        assert "t+1" in (sell.reject_reason or "").lower()

    def test_cn_sell_allowed_next_day(self, broker: PaperBroker) -> None:
        buy = broker.place_order("cn", "600519", "buy", 100)
        assert buy.status == "filled"
        broker.clock["now"] = datetime(2024, 6, 11, 10, 0, 0)
        sell = broker.place_order("cn", "600519", "sell", 100)
        assert sell.status == "filled"
        assert broker.get_position("cn", "600519") is None or broker.get_position(
            "cn", "600519"
        ).quantity == 0

    def test_hk_enforces_known_lot(self, broker: PaperBroker) -> None:
        bad = broker.place_order("hk", "0700", "buy", 50)
        assert bad.status == "rejected"
        good = broker.place_order("hk", "0700", "buy", 100)
        assert good.status == "filled"


def _seed_zero_qty_residue(session, *, now: datetime) -> dict:
    """Isolation-migration leftovers: qty=0 rows on several books, plus one live pos."""
    accounts = {a.market_id: a for a in session.query(Account).all()}
    zeros = [
        Position(account_id=accounts["us"].id, market_id="us", symbol="RESIDUE.US", quantity=0, avg_cost=0.0),
        Position(account_id=accounts["hk"].id, market_id="hk", symbol="RESIDUE.HK", quantity=0, avg_cost=12.0),
        Position(account_id=accounts["cn"].id, market_id="cn", symbol="RESIDUE.CN", quantity=0, avg_cost=0.0),
    ]
    live = Position(
        account_id=accounts["us_book"].id,
        market_id="us_book",
        symbol="AAPL",
        quantity=7,
        avg_cost=100.0,
    )
    session.add_all([*zeros, live])
    session.flush()
    session.add_all(
        [
            PositionLot(
                position_id=zeros[0].id,
                quantity=10,
                remaining=0,
                price=1.0,
                acquired_on=now,
            ),
            PositionLot(
                position_id=live.id,
                quantity=7,
                remaining=7,
                price=100.0,
                acquired_on=now,
            ),
            PositionLot(
                position_id=9_999_999,
                quantity=3,
                remaining=0,
                price=2.0,
                acquired_on=now,
            ),
            Order(
                account_id=accounts["us"].id,
                market_id="us",
                symbol="RESIDUE.US",
                side="sell",
                quantity=10,
                status="filled",
                fill_price=1.0,
                created_at=now,
                fill_time=now,
            ),
        ]
    )
    accounts["us"].cash = 88_000.0
    session.commit()
    return {
        "live_id": live.id,
        "zero_ids": [z.id for z in zeros],
        "cash": {a.market_id: a.cash for a in session.query(Account).all()},
        "orders": [
            (o.id, o.market_id, o.symbol, o.quantity, o.status)
            for o in session.query(Order).order_by(Order.id).all()
        ],
    }


def _assert_residue_cleared(session, seed: dict) -> None:
    leftover = session.query(Position).filter(Position.quantity <= 0).all()
    assert leftover == []
    live = session.query(Position).filter_by(id=seed["live_id"]).one()
    assert live.quantity == 7
    assert live.symbol == "AAPL"
    assert live.market_id == "us_book"
    live_lots = session.query(PositionLot).filter_by(position_id=live.id).all()
    assert len(live_lots) == 1
    assert live_lots[0].remaining == 7
    assert session.query(PositionLot).filter_by(position_id=9_999_999).all() == []
    assert session.query(PositionLot).filter(PositionLot.position_id.in_(seed["zero_ids"])).all() == []
    cash = {a.market_id: a.cash for a in session.query(Account).all()}
    assert cash == seed["cash"]
    orders = [
        (o.id, o.market_id, o.symbol, o.quantity, o.status)
        for o in session.query(Order).order_by(Order.id).all()
    ]
    assert orders == seed["orders"]


class TestZeroQuantityCleanup:
    def test_purge_drops_zero_qty_and_orphans_keeps_live(self, tmp_path) -> None:
        session = create_session(f"sqlite:///{tmp_path / 'paper.db'}")
        now = datetime(2024, 6, 10, 10, 0, 0)
        broker = PaperBroker(session, registry=_registry(), now=lambda: now)
        broker.ensure_accounts()
        seed = _seed_zero_qty_residue(session, now=now)

        stats = purge_zero_quantity_positions(session)
        assert stats["positions"] == 3
        assert stats["lots"] >= 2
        _assert_residue_cleared(session, seed)

        again = purge_zero_quantity_positions(session)
        assert again["positions"] == 0
        assert again["lots"] == 0
        _assert_residue_cleared(session, seed)

    def test_ensure_accounts_purges_zero_qty_residue(self, tmp_path) -> None:
        session = create_session(f"sqlite:///{tmp_path / 'paper.db'}")
        now = datetime(2024, 6, 10, 10, 0, 0)
        broker = PaperBroker(session, registry=_registry(), now=lambda: now)
        broker.ensure_accounts()
        seed = _seed_zero_qty_residue(session, now=now)

        broker.ensure_accounts()
        _assert_residue_cleared(session, seed)
