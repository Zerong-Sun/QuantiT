"""Tests for Phase 1 components."""

import pandas as pd
import pytest

from quantit.analysis.metrics import compute_metrics
from quantit.engine.backtester import Backtester
from quantit.engine.broker import Broker, OrderStatus
from quantit.engine.portfolio import Portfolio
from quantit.strategy.technical import MACrossoverStrategy


def _make_ohlcv(n: int = 100, start_price: float = 100.0) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    prices = [start_price + i * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [1_000_000] * n,
        },
        index=dates,
    )


class TestPortfolio:
    def test_buy_and_sell(self) -> None:
        p = Portfolio(initial_cash=10_000)
        p.buy("AAPL", 10, 100.0, commission=1.0)
        assert p.get_position("AAPL").quantity == 10
        assert p.cash == 10_000 - 1001

        p.sell("AAPL", 10, 110.0, commission=1.1)
        assert p.get_position("AAPL").quantity == 0
        assert p.cash > 10_000

    def test_equity(self) -> None:
        p = Portfolio(initial_cash=10_000)
        p.buy("AAPL", 10, 100.0)
        assert p.equity({"AAPL": 110.0}) == 10_000 - 1000 + 1100

    def test_market_value_uses_mark(self) -> None:
        p = Portfolio(initial_cash=10_000)
        p.buy("AAPL", 10, 100.0)
        pos = p.get_position("AAPL")
        assert pos.market_value(110.0) == 1100.0
        assert pos.market_value() == 1000.0

    def test_insufficient_cash(self) -> None:
        p = Portfolio(initial_cash=100)
        with pytest.raises(ValueError, match="Insufficient cash"):
            p.buy("AAPL", 10, 100.0)


class TestBroker:
    def test_submit_buy(self) -> None:
        p = Portfolio(initial_cash=10_000)
        broker = Broker(p, commission_rate=0.0, slippage_rate=0.0)
        order = broker.buy("AAPL", 10, 100.0, pd.Timestamp("2020-01-01"))
        assert order.status == OrderStatus.FILLED
        assert len(broker.trades) == 1

    def test_insufficient_cash_rejects(self) -> None:
        p = Portfolio(initial_cash=50)
        broker = Broker(p, commission_rate=0.0, slippage_rate=0.0)
        order = broker.buy("AAPL", 10, 100.0, pd.Timestamp("2020-01-01"))
        assert order.status == OrderStatus.REJECTED
        assert p.cash == 50
        assert len(broker.trades) == 0


class TestBacktester:
    def test_run_ma_crossover(self) -> None:
        data = _make_ohlcv(100)
        strategy = MACrossoverStrategy(fast_period=5, slow_period=20)
        result = Backtester(initial_cash=100_000).run(strategy, data, symbol="TEST")
        assert not result.equity_curve.empty
        assert result.equity_curve.iloc[0] == 100_000
        metrics = compute_metrics(result)
        assert "win_rate" in metrics
        assert metrics["total_trades"] == float(len(result.trades))

    def test_idle_book_sharpe_is_finite(self) -> None:
        from quantit.strategy.base import Context, Strategy

        class Idle(Strategy):
            def on_bar(self, context: Context, bar: pd.Series) -> None:
                return

        data = _make_ohlcv(80)
        result = Backtester(initial_cash=100_000).run(Idle(), data, symbol="CASH")
        metrics = compute_metrics(result)
        assert metrics["total_trades"] == 0
        assert abs(metrics["sharpe_ratio"]) < 10
        import math

        assert math.isfinite(metrics["sharpe_ratio"])
