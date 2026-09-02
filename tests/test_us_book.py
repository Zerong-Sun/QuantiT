"""USBookStrategy matches resolve_us_book_action on each bar."""

from __future__ import annotations

import pandas as pd

from quantit.engine.backtester import Backtester
from quantit.features.technical import RSIFeature, SMAFeature
from quantit.strategy.signals import resolve_us_book_action
from quantit.strategy.technical import ma_cross_side, rsi_reversion_side
from quantit.strategy.us_book import USBookStrategy


def _ohlcv(prices: list[float], start: str = "2020-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(prices), freq="B")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [1_000_000.0] * len(prices),
        },
        index=dates,
    )


def _book_action(fast_prev, slow_prev, fast_curr, slow_curr, rsi, buy_th, sell_th) -> str:
    ma_side = ma_cross_side(fast_prev, slow_prev, fast_curr, slow_curr)
    rsi_side = rsi_reversion_side(rsi, buy_th, sell_th)
    ma = {
        "action": ma_side or "hold",
        "reason": "crossed below" if ma_side == "sell" else ("crossed above" if ma_side == "buy" else "hold"),
        "values": {"fast_ma": fast_curr, "slow_ma": slow_curr},
    }
    rsi_d = {
        "action": rsi_side or "hold",
        "reason": "oversold" if rsi_side == "buy" else ("overbought" if rsi_side == "sell" else "hold"),
        "values": {"rsi": rsi},
    }
    return resolve_us_book_action(ma, rsi_d)["action"]


def test_us_book_buys_remaining_uptrend_without_waiting_for_cross() -> None:
    prices = [100.0 + i * 0.5 for i in range(80)]
    data = _ohlcv(prices)
    result = Backtester(initial_cash=100_000, commission_rate=0.0, slippage_rate=0.0).run(
        USBookStrategy(fast_period=10, slow_period=30, position_pct=0.95),
        data,
        symbol="TEST",
    )
    assert result.trades
    assert result.trades[0].side.value == "buy"


def test_us_book_action_matches_resolve_us_book_action() -> None:
    prices = [100.0 + i * 0.4 for i in range(40)] + [116.0 - i * 1.2 for i in range(40)]
    data = _ohlcv(prices)
    strat = USBookStrategy(fast_period=10, slow_period=30, period=14, buy_threshold=30, sell_threshold=70)
    fast = SMAFeature(period=10).compute(data)
    slow = SMAFeature(period=30).compute(data)
    rsi = RSIFeature(period=14).compute(data)
    for i in range(30, len(data)):
        expected = _book_action(
            float(fast.iloc[i - 1]),
            float(slow.iloc[i - 1]),
            float(fast.iloc[i]),
            float(slow.iloc[i]),
            float(rsi.iloc[i]),
            30,
            70,
        )
        got = strat.action_for_bar(i, fast, slow, rsi)
        assert got == expected, f"bar {i}: {got} != {expected}"
