"""Live trading reasons from the strategies in the catalog."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from quantit.features.technical import RSIFeature, SMAFeature
from quantit.markets.hk import HK_NAMES, theme_of
from quantit.strategy.catalog import get_strategy, list_strategies
from quantit.strategy.technical import (
    MACrossoverStrategy,
    RSIMeanReversionStrategy,
    ma_cross_side,
    rsi_reversion_side,
)


def _at(series: pd.Series, offset: int) -> float | None:
    """Value at ``iloc[-1 - offset]`` without skipping NaNs."""
    if series is None or len(series) <= offset:
        return None
    val = series.iloc[-1 - offset]
    if pd.isna(val):
        return None
    return float(val)


def _asof(index) -> str | None:
    if index is None or len(index) == 0:
        return None
    ts = pd.Timestamp(index[-1])
    return ts.isoformat()


def ma_signal(bars: pd.DataFrame) -> dict[str, Any]:
    entry = get_strategy("ma_crossover") or {}
    defaults = MACrossoverStrategy()
    fast_p = defaults.fast_period
    slow_p = defaults.slow_period
    values: dict[str, Any] = {"fast_period": fast_p, "slow_period": slow_p}
    out = {
        "strategy_id": "ma_crossover",
        "name": entry.get("name", "MA Crossover"),
        "action": "hold",
        "reason": f"Need at least {slow_p + 1} daily bars to evaluate SMA({fast_p}) / SMA({slow_p}).",
        "values": values,
    }
    if bars is None or bars.empty or "close" not in bars.columns:
        return out
    if len(bars) < slow_p + 1:
        return out

    fast = SMAFeature(period=fast_p).compute(bars)
    slow = SMAFeature(period=slow_p).compute(bars)
    fast_curr = _at(fast, 0)
    slow_curr = _at(slow, 0)
    fast_prev = _at(fast, 1)
    slow_prev = _at(slow, 1)
    values.update({"fast_ma": fast_curr, "slow_ma": slow_curr})
    if fast_curr is None or slow_curr is None or fast_prev is None or slow_prev is None:
        out["reason"] = "SMA not available on the latest daily bars."
        return out

    side = ma_cross_side(fast_prev, slow_prev, fast_curr, slow_curr)
    if side == "buy":
        out["action"] = "buy"
        out["reason"] = (
            f"SMA({fast_p})={fast_curr:.2f} crossed above SMA({slow_p})={slow_curr:.2f}. "
            "Trend-following rule: buy if flat."
        )
    elif side == "sell":
        out["action"] = "sell"
        out["reason"] = (
            f"SMA({fast_p})={fast_curr:.2f} crossed below SMA({slow_p})={slow_curr:.2f}. "
            "Trend-following rule: sell if long."
        )
    elif fast_curr > slow_curr:
        out["reason"] = (
            f"SMA({fast_p})={fast_curr:.2f} remains above SMA({slow_p})={slow_curr:.2f}; no new cross."
        )
    else:
        out["reason"] = (
            f"SMA({fast_p})={fast_curr:.2f} remains below SMA({slow_p})={slow_curr:.2f}; no new cross."
        )
    return out


def rsi_signal(bars: pd.DataFrame) -> dict[str, Any]:
    entry = get_strategy("rsi_mean_reversion") or {}
    defaults = RSIMeanReversionStrategy()
    period = defaults.period
    buy_th = defaults.buy_threshold
    sell_th = defaults.sell_threshold
    values: dict[str, Any] = {
        "period": period,
        "buy_threshold": buy_th,
        "sell_threshold": sell_th,
    }
    out = {
        "strategy_id": "rsi_mean_reversion",
        "name": entry.get("name", "RSI Mean Reversion"),
        "action": "hold",
        "reason": f"Need enough daily bars to compute RSI({period}).",
        "values": values,
    }
    if bars is None or bars.empty or "close" not in bars.columns:
        return out
    rsi = RSIFeature(period=period).compute(bars)
    val = _at(rsi, 0)
    values["rsi"] = val
    if val is None:
        return out
    side = rsi_reversion_side(val, buy_th, sell_th)
    if side == "buy":
        out["action"] = "buy"
        out["reason"] = (
            f"RSI({period})={val:.1f} is below {buy_th:.0f} (oversold). "
            "Mean-reversion rule: buy if flat."
        )
    elif side == "sell":
        out["action"] = "sell"
        out["reason"] = (
            f"RSI({period})={val:.1f} is above {sell_th:.0f} (overbought). "
            "Mean-reversion rule: sell if long."
        )
    else:
        out["reason"] = (
            f"RSI({period})={val:.1f} is between {buy_th:.0f} and {sell_th:.0f}; no mean-reversion trigger."
        )
    return out


def theme_signal(symbol: str) -> dict[str, Any]:
    entry = get_strategy("theme_rotation") or {}
    theme = theme_of(symbol)
    values: dict[str, Any] = {
        "theme": theme,
        "name": HK_NAMES.get(symbol, symbol),
        "score_weights": entry.get("score_weights"),
    }
    out = {
        "strategy_id": "theme_rotation",
        "name": entry.get("name", "HK Tech Theme Rotation"),
        "action": "watch",
        "reason": "",
        "values": values,
    }
    if theme is None:
        out["action"] = "hold"
        out["reason"] = (
            f"{symbol} is outside the Hang Seng TECH rotation universe "
            "(platforms / hardware / semis / EV). No monthly sleeve weight."
        )
        return out
    out["reason"] = (
        f"{symbol} ({HK_NAMES.get(symbol, symbol)}) sits in the {theme} sleeve. "
        "Membership only — rebalance is monthly on the last HK session, not a daily buy/sell."
    )
    return out


_SIGNAL_FNS = {
    "ma_crossover": lambda bars, symbol: ma_signal(bars),
    "rsi_mean_reversion": lambda bars, symbol: rsi_signal(bars),
    "theme_rotation": lambda bars, symbol: theme_signal(symbol),
}


def evaluate_signals(market: str, symbol: str, bars: pd.DataFrame) -> dict[str, Any]:
    """Return per-strategy reasons for strategies that apply to this market."""
    signals: list[dict[str, Any]] = []
    for entry in list_strategies(market):
        fn = _SIGNAL_FNS.get(entry["id"])
        if fn is None:
            continue
        signals.append(fn(bars, symbol))
    headline = next((s for s in signals if s["action"] in {"buy", "sell"}), None)
    if headline is None and signals:
        headline = signals[0]
    return {
        "market_id": market,
        "symbol": symbol,
        "asof": _asof(bars.index if bars is not None and not bars.empty else None),
        "headline": headline["reason"] if headline else "No strategy wired for this market.",
        "signals": signals,
        "evaluated_at": datetime.utcnow().isoformat() + "Z",
    }
