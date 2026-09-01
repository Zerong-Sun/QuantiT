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
from quantit.paper.db import create_session


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
        assert set(accounts) == {"us", "hk", "cn"}
        assert accounts["us"].currency == "USD"
        assert accounts["hk"].currency == "HKD"
        assert accounts["cn"].currency == "CNY"
        assert accounts["us"].cash == 100_000.0


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
