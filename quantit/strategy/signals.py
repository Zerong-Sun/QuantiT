"""Live trading reasons from the strategies in the catalog."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from quantit.features.technical import RSIFeature, SMAFeature, VolatilityFeature
from quantit.markets.cn import CN_ETF_NAMES, canonical_cn_symbol, cn_theme_of
from quantit.markets.hk import HK_NAMES, theme_of
from quantit.research.params import strategy_params, us_primary
from quantit.strategy.catalog import get_strategy, list_strategies
from quantit.strategy.technical import (
    MACrossoverStrategy,
    RSIMeanReversionStrategy,
    ma_cross_side,
    rsi_reversion_side,
)
from quantit.strategy.tsmom import TSMOMStrategy, tsmom_momentum


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
    cfg = strategy_params("ma_crossover")
    fast_p = int(cfg.get("fast_period", defaults.fast_period))
    slow_p = int(cfg.get("slow_period", defaults.slow_period))
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
    cfg = strategy_params("rsi_mean_reversion")
    period = int(cfg.get("period", defaults.period))
    buy_th = float(cfg.get("buy_threshold", defaults.buy_threshold))
    sell_th = float(cfg.get("sell_threshold", defaults.sell_threshold))
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


def resolve_us_book_action(ma: dict[str, Any], rsi: dict[str, Any]) -> dict[str, Any]:
    """Pick one paper action so trend-follow and mean-reversion do not share a slot.

    Uptrend (fast SMA > slow SMA): MA only. Remaining-above is a buy so a live
    book can enter without waiting for the next cross. RSI overbought is ignored.
    Death-cross sell always wins, even if RSI is oversold.
    Downtrend: RSI only (oversold buy / overbought sell).
    """
    values = dict(ma.get("values") or {})
    values.update(rsi.get("values") or {})
    fast = values.get("fast_ma")
    slow = values.get("slow_ma")
    base = {
        "strategy_id": "us_book",
        "name": "US book",
        "action": "hold",
        "reason": "Need SMA(fast) and SMA(slow) to choose trend vs reversion.",
        "values": values,
        "mode": "unknown",
    }
    if fast is None or slow is None:
        return base

    if ma.get("action") == "sell":
        return {
            "strategy_id": "us_book",
            "name": "US book",
            "action": "sell",
            "reason": ma.get("reason") or "SMA death cross; exit trend long.",
            "values": values,
            "mode": "trend",
        }

    if float(fast) > float(slow):
        reason = ma.get("reason") or ""
        if ma.get("action") == "buy":
            text = reason
        else:
            text = (
                f"SMA fast {float(fast):.2f} is above slow {float(slow):.2f}; "
                "trend-following rule: buy if flat (no need to wait for a new cross)."
            )
        return {
            "strategy_id": "us_book",
            "name": "US book",
            "action": "buy",
            "reason": text,
            "values": values,
            "mode": "trend",
        }

    return {
        "strategy_id": "us_book",
        "name": "US book",
        "action": rsi.get("action") or "hold",
        "reason": (
            (rsi.get("reason") or "RSI hold")
            + " Trend is down, so mean-reversion is armed and MA entries are ignored."
        ),
        "values": values,
        "mode": "reversion",
    }


def tsmom_signal(bars: pd.DataFrame) -> dict[str, Any]:
    entry = get_strategy("tsmom") or {}
    defaults = TSMOMStrategy()
    cfg = strategy_params("tsmom")
    lookback = int(cfg.get("lookback", defaults.lookback))
    skip = int(cfg.get("skip", defaults.skip))
    target_vol = float(cfg.get("target_vol", defaults.target_vol))
    vol_lookback = int(cfg.get("vol_lookback", defaults.vol_lookback))
    risk_off_scale = float(cfg.get("risk_off_scale", defaults.risk_off_scale))
    values: dict[str, Any] = {
        "lookback": lookback,
        "skip": skip,
        "target_vol": target_vol,
        "vol_lookback": vol_lookback,
        "risk_off_scale": risk_off_scale,
    }
    out = {
        "strategy_id": "tsmom",
        "name": entry.get("name", "Time-Series Momentum"),
        "action": "hold",
        "reason": f"Need at least {lookback + 1} daily bars to evaluate skipped lookback return.",
        "values": values,
    }
    if bars is None or bars.empty or "close" not in bars.columns:
        return out
    if len(bars) < lookback + 1:
        return out
    mom = tsmom_momentum(bars["close"], lookback, skip)
    vol = VolatilityFeature(period=vol_lookback).compute(bars)
    mom_val = _at(mom, 0)
    vol_val = _at(vol, 0)
    values["momentum"] = mom_val
    values["realized_vol"] = vol_val
    if mom_val is None:
        out["reason"] = "Momentum not available on the latest daily bars."
        return out
    if mom_val > 0:
        out["action"] = "buy"
        out["reason"] = (
            f"Skipped {lookback}-bar return is {mom_val:.2%}; "
            f"time-series momentum is positive (vol target {target_vol:.0%})."
        )
    else:
        out["action"] = "sell"
        out["reason"] = (
            f"Skipped {lookback}-bar return is {mom_val:.2%}; "
            f"time-series momentum is non-positive, scale to {risk_off_scale:.0%} of vol target."
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


def cn_etf_signal(symbol: str) -> dict[str, Any]:
    entry = get_strategy("cn_etf_rotation") or {}
    canonical = canonical_cn_symbol(symbol)
    theme = cn_theme_of(canonical)
    label = CN_ETF_NAMES.get(canonical, symbol)
    values: dict[str, Any] = {
        "theme": theme,
        "name": label,
        "score_weights": entry.get("score_weights"),
    }
    out = {
        "strategy_id": "cn_etf_rotation",
        "name": entry.get("name", "CN Industry ETF Rotation"),
        "action": "watch",
        "reason": "",
        "values": values,
    }
    if theme is None:
        out["action"] = "hold"
        out["reason"] = (
            f"{symbol} is outside the A-share industry ETF rotation universe "
            "(semis / ev / healthcare / defense). No monthly sleeve weight."
        )
        return out
    out["reason"] = (
        f"{symbol} ({label}) sits in the {theme} sleeve. "
        "Membership only — rebalance is monthly on the last A-share session, not a daily buy/sell."
    )
    return out


_SIGNAL_FNS = {
    "ma_crossover": lambda bars, symbol: ma_signal(bars),
    "rsi_mean_reversion": lambda bars, symbol: rsi_signal(bars),
    "tsmom": lambda bars, symbol: tsmom_signal(bars),
    "theme_rotation": lambda bars, symbol: theme_signal(symbol),
    "cn_etf_rotation": lambda bars, symbol: cn_etf_signal(symbol),
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
    if market == "us":
        ma = next((s for s in signals if s["strategy_id"] == "ma_crossover"), None)
        rsi = next((s for s in signals if s["strategy_id"] == "rsi_mean_reversion"), None)
        tsmom = next((s for s in signals if s["strategy_id"] == "tsmom"), None)
        if ma is not None and rsi is not None:
            book = resolve_us_book_action(ma, rsi)
            signals = [book, *signals]
            if us_primary() == "tsmom" and tsmom is not None:
                headline = tsmom
            else:
                headline = book
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
