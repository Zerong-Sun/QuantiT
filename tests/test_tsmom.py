"""TSMOM: 12-month sign plus volatility targeting."""

from __future__ import annotations

import pandas as pd
import pytest

from quantit.engine.backtester import Backtester
from quantit.strategy.tsmom import TSMOMStrategy, coerce_vol, tsmom_momentum, tsmom_size


def _ohlcv(prices: list[float], start: str = "2018-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(prices), freq="B")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [max(0.1, p - 0.5) for p in prices],
            "close": prices,
            "volume": [1_000_000.0] * len(prices),
        },
        index=dates,
    )


def test_momentum_skip_uses_lagged_return() -> None:
    prices = [float(i) for i in range(1, 30)]
    mom = tsmom_momentum(pd.Series(prices), lookback=10, skip=2)
    # close[t-2]/close[t-10] - 1 at t=10: prices[8]/prices[0] - 1 = 9/1 - 1
    assert mom.iloc[10] == pytest.approx(8.0)


def test_tsmom_holds_through_uptrend() -> None:
    prices = [100.0 * (1.002 ** i) for i in range(400)]
    data = _ohlcv(prices)
    result = Backtester(initial_cash=100_000, commission_rate=0.0, slippage_rate=0.0).run(
        TSMOMStrategy(lookback=126, skip=21, target_vol=0.15, vol_lookback=20),
        data,
        symbol="TREND",
    )
    assert result.trades
    assert result.trades[0].side.value == "buy"
    assert result.portfolio.get_position("TREND").quantity > 0


def test_tsmom_stays_cash_in_downtrend() -> None:
    prices = [200.0 * (0.997 ** i) for i in range(400)]
    data = _ohlcv(prices)
    result = Backtester(initial_cash=100_000, commission_rate=0.0, slippage_rate=0.0).run(
        TSMOMStrategy(lookback=126, skip=21, target_vol=0.15, vol_lookback=20),
        data,
        symbol="DROP",
    )
    longs = [t for t in result.trades if t.side.value == "buy"]
    assert result.portfolio.get_position("DROP").quantity == 0
    assert not longs or result.equity_curve.iloc[-1] <= result.equity_curve.iloc[0] * 1.02


def test_higher_vol_reduces_size() -> None:
    low = tsmom_size(equity=100_000, price=100.0, realized_vol=0.10, target_vol=0.15, vol_floor=0.05, max_position_pct=0.95)
    high = tsmom_size(equity=100_000, price=100.0, realized_vol=0.30, target_vol=0.15, vol_floor=0.05, max_position_pct=0.95)
    assert high < low
    assert low > 0


def test_tsmom_size_rejects_non_finite_vol() -> None:
    assert tsmom_size(100_000, 100.0, float("nan"), 0.15, 0.05, 0.95) == 0
    assert tsmom_size(100_000, 100.0, float("inf"), 0.15, 0.05, 0.95) == 0
    assert tsmom_size(100_000, 0.0, 0.10, 0.15, 0.05, 0.95) == 0


def test_coerce_vol_falls_back() -> None:
    assert coerce_vol(float("nan")) == 0.15
    assert coerce_vol(None) == 0.15
    assert coerce_vol(0.0) == 0.15
    assert coerce_vol(0.22) == pytest.approx(0.22)
