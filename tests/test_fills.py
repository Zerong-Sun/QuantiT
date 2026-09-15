"""F2: research next_open vs paper delayed-last-close (synthetic, no network)."""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from quantit.data.provider import DataProvider
from quantit.engine.backtester import Backtester
from quantit.engine.broker import Order
from quantit.markets.registry import MarketRegistry
from quantit.markets.us import US_PROFILE, USAdapter
from quantit.paper.broker import PaperBroker
from quantit.paper.db import create_session
from quantit.research.fills import (
    PAPER_FILL_ANALOG,
    RESEARCH_FILL_ON,
    apply_slippage,
    compare_fill_models,
    paper_fill_price,
    research_fill_price,
    research_uses_walk_forward_fill,
)
from quantit.research.search import grid_search, run_backtest
from quantit.research.walk_forward import walk_forward
from quantit.strategy.base import Context, Strategy
from quantit.utils.config import get_config


def _gap_bars(n: int = 80, start: str = "2020-01-02") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    close = [100.0 + i * 0.4 for i in range(n)]
    # Opens gap away from the prior close so next_open fills differ from same_close.
    open_px = [c * 1.01 for c in close]
    return pd.DataFrame(
        {
            "open": open_px,
            "high": [o + 0.5 for o in open_px],
            "low": [c - 0.5 for c in close],
            "close": close,
            "volume": [1_000_000.0] * n,
        },
        index=dates,
    )


def _timing_bars() -> pd.DataFrame:
    """Three sessions where open != close so next_open and delayed-close cannot coincide."""
    dates = pd.date_range("2024-06-03", periods=3, freq="B")
    return pd.DataFrame(
        {
            "open": [100.0, 110.0, 120.0],
            "high": [106.0, 116.0, 126.0],
            "low": [99.0, 109.0, 119.0],
            "close": [105.0, 115.0, 125.0],
            "volume": [1_000_000.0] * 3,
        },
        index=dates,
    )


class BuyOnceStrategy(Strategy):
    """Buy 1 share on the first bar only."""

    def __init__(self) -> None:
        self.fills: list[Order] = []
        self.bought = False

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if not self.bought:
            context.buy(1)
            self.bought = True

    def on_order(self, context: Context, order: Order) -> None:
        self.fills.append(order)


class FakeProvider(DataProvider):
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def fetch(self, symbol, start, end, interval: str = "1d") -> pd.DataFrame:
        if symbol not in self.frames:
            raise ValueError(f"No data returned for {symbol}")
        return self.frames[symbol].copy()


def test_compare_fill_models_reports_delta() -> None:
    data = _gap_bars()
    row = compare_fill_models(
        "tsmom",
        {"lookback": 20, "skip": 0, "target_vol": 0.15, "vol_lookback": 10},
        data,
        symbol="GAP",
        initial_cash=100_000.0,
        slippage_rate=0.0005,
    )
    assert "next_open" in row and "same_close_slip" in row
    assert "delta_sharpe" in row and "delta_dd" in row
    assert row["next_open"].get("sharpe_ratio") is not None
    assert row["same_close_slip"].get("sharpe_ratio") is not None
    assert row["fill_on_research"] == RESEARCH_FILL_ON == "next_open"
    assert row["fill_on_paper"] == PAPER_FILL_ANALOG == "same_close"
    assert row["research_matches_walk_forward"] is True
    assert research_uses_walk_forward_fill() is True


def test_fill_timing_contract_is_intentional_gap() -> None:
    """Research and paper must stay on different fill clocks (F2)."""
    assert RESEARCH_FILL_ON != PAPER_FILL_ANALOG
    assert get_config().fill_on == RESEARCH_FILL_ON
    assert "fill_on" not in inspect.signature(walk_forward).parameters
    assert "fill_on" not in inspect.signature(grid_search).parameters
    assert inspect.signature(run_backtest).parameters["fill_on"].default is None
    engine = Backtester(initial_cash=10_000, commission_rate=0.0, slippage_rate=0.0)
    assert engine.fill_on == RESEARCH_FILL_ON


def test_research_fill_is_next_bar_open_not_signal_close() -> None:
    data = _timing_bars()
    result = Backtester(initial_cash=10_000, commission_rate=0.0, slippage_rate=0.0).run(
        BuyOnceStrategy(), data, symbol="GAP"
    )
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.timestamp == data.index[1].to_pydatetime()
    expected = research_fill_price(float(data["open"].iloc[1]), side="buy", slippage_rate=0.0)
    assert trade.price == pytest.approx(expected)
    assert trade.price == pytest.approx(110.0)
    assert trade.price != pytest.approx(float(data["close"].iloc[0]))
    assert trade.price != pytest.approx(float(data["close"].iloc[-1]))


def test_paper_fill_is_delayed_last_close_not_next_open() -> None:
    data = _timing_bars()
    registry = MarketRegistry()
    registry.register(USAdapter(provider=FakeProvider({"AAPL": data})))
    broker = PaperBroker(
        create_session("sqlite:///:memory:"),
        registry=registry,
        now=lambda: data.index[-1].to_pydatetime(),
    )
    broker.ensure_accounts(cash=100_000.0)

    quote = broker.adapter_for("us").fetch_quote("AAPL")
    assert quote.delayed is True
    assert quote.last == pytest.approx(float(data["close"].iloc[-1]))
    assert quote.last != pytest.approx(float(data["open"].iloc[-1]))
    assert quote.open == pytest.approx(float(data["open"].iloc[-1]))

    order = broker.place_order("us", "AAPL", "buy", 10)
    assert order.status == "filled"
    expected = paper_fill_price(
        float(data["close"].iloc[-1]),
        side="buy",
        slippage_rate=US_PROFILE.slippage_rate,
    )
    assert order.fill_price == pytest.approx(expected)
    # Delayed last close (125) ± slip, not last open (120).
    assert order.fill_price != pytest.approx(research_fill_price(float(data["open"].iloc[-1])))
    assert order.fill_price != pytest.approx(float(data["open"].iloc[-1]))
    assert order.fill_time == data.index[-1].to_pydatetime()


def test_research_and_paper_prices_diverge_on_gapped_bars() -> None:
    """Same tape, two clocks: next open vs delayed close. Gap is the product, not a bug."""
    data = _timing_bars()
    slip = US_PROFILE.slippage_rate
    next_open = research_fill_price(float(data["open"].iloc[1]), side="buy", slippage_rate=slip)
    delayed_close = paper_fill_price(float(data["close"].iloc[-1]), side="buy", slippage_rate=slip)
    assert next_open == pytest.approx(apply_slippage(110.0, side="buy", slippage_rate=slip))
    assert delayed_close == pytest.approx(apply_slippage(125.0, side="buy", slippage_rate=slip))
    assert next_open != pytest.approx(delayed_close)

    research = Backtester(
        initial_cash=10_000,
        commission_rate=0.0,
        slippage_rate=slip,
    ).run(BuyOnceStrategy(), data, symbol="GAP")
    registry = MarketRegistry()
    registry.register(USAdapter(provider=FakeProvider({"AAPL": data})))
    paper = PaperBroker(
        create_session("sqlite:///:memory:"),
        registry=registry,
        now=lambda: data.index[-1].to_pydatetime(),
    )
    paper.ensure_accounts(cash=100_000.0)
    paper_order = paper.place_order("us", "AAPL", "buy", 1)

    assert research.trades[0].price == pytest.approx(next_open)
    assert paper_order.fill_price == pytest.approx(delayed_close)
    assert research.trades[0].price != pytest.approx(paper_order.fill_price)


def test_run_backtest_default_fill_on_is_config_next_open() -> None:
    """walk_forward / grid_search never pass fill_on; None must mean next_open."""
    assert inspect.signature(run_backtest).parameters["fill_on"].default is None
    data = _timing_bars()
    default = Backtester(initial_cash=10_000, commission_rate=0.0, slippage_rate=0.0)
    explicit = Backtester(
        initial_cash=10_000,
        commission_rate=0.0,
        slippage_rate=0.0,
        fill_on=RESEARCH_FILL_ON,
    )
    a = default.run(BuyOnceStrategy(), data, symbol="GAP")
    b = explicit.run(BuyOnceStrategy(), data, symbol="GAP")
    assert default.fill_on == RESEARCH_FILL_ON
    assert a.trades[0].price == b.trades[0].price == pytest.approx(110.0)
    assert a.trades[0].timestamp == b.trades[0].timestamp == data.index[1].to_pydatetime()
