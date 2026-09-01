"""Live strategy catalog for the paper terminal.

Parameter values are read from strategy ``__init__`` defaults and from the
HK universe / score-weight constants, so the UI stays in sync when those
change. Narrative copy lives here — update it in the same change as the
strategy logic.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from quantit.features.regime import DEMAND_WEIGHT, INTL_WEIGHT, POLICY_WEIGHT
from quantit.markets.hk import HK_NAMES, HSTECH_THEMES
from quantit.strategy.regime import ThemeRotationStrategy
from quantit.strategy.technical import MACrossoverStrategy, RSIMeanReversionStrategy

PARAM_HELP: dict[str, str] = {
    "fast_period": "Fast SMA lookback (bars).",
    "slow_period": "Slow SMA lookback (bars).",
    "position_pct": "Fraction of cash to deploy on a buy.",
    "period": "RSI lookback (bars).",
    "buy_threshold": "Buy when RSI is below this.",
    "sell_threshold": "Sell when RSI is above this.",
    "cash_threshold": "If the best theme score is below this, raise cash.",
    "risk_off_invested": "Target invested weight in risk-off (rest is cash).",
    "equal_weight_band": "If theme-score range is tighter than this, equal-weight.",
    "turnover_band": "Skip a name if the qty change vs current is within this band.",
}


def _init_defaults(cls: type, skip: frozenset[str] = frozenset()) -> dict[str, Any]:
    sig = inspect.signature(cls.__init__)
    out: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "self" or name in skip:
            continue
        if param.default is inspect.Parameter.empty:
            continue
        out[name] = param.default
    return out


def _params(cls: type, skip: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    rows = []
    for name, value in _init_defaults(cls, skip=skip).items():
        rows.append(
            {
                "name": name,
                "value": value,
                "type": type(value).__name__,
                "description": PARAM_HELP.get(name, ""),
            }
        )
    return rows


def _theme_universe() -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for theme, members in HSTECH_THEMES.items():
        out[theme] = [{"symbol": s, "name": HK_NAMES.get(s, s)} for s in members]
    return out


def _ma_entry() -> dict[str, Any]:
    return {
        "id": "ma_crossover",
        "name": "MA Crossover",
        "class_name": MACrossoverStrategy.__name__,
        "markets": ["us"],
        "horizon": "Daily, single-name",
        "summary": inspect.getdoc(MACrossoverStrategy) or "",
        "thesis": (
            "Trend following. A fast SMA crossing above a slow SMA is treated as "
            "momentum turning up; a cross below as momentum turning down. Used on "
            "US single names at daily bars."
        ),
        "rules": [
            "If fast SMA crosses above slow SMA and the book is flat, buy with position_pct of cash.",
            "If fast SMA crosses below slow SMA and a long is held, sell all.",
            "Backtests fill on the next bar's open. Paper terminal is manual; this card is the live rule set.",
        ],
        "parameters": _params(MACrossoverStrategy),
        "universe": None,
        "score_weights": None,
    }


def _rsi_entry() -> dict[str, Any]:
    return {
        "id": "rsi_mean_reversion",
        "name": "RSI Mean Reversion",
        "class_name": RSIMeanReversionStrategy.__name__,
        "markets": ["us"],
        "horizon": "Daily, single-name",
        "summary": inspect.getdoc(RSIMeanReversionStrategy) or "",
        "thesis": (
            "Mean reversion. RSI below the buy threshold is treated as short-term "
            "oversold; above the sell threshold as overbought. Used on US single names."
        ),
        "rules": [
            "If RSI < buy_threshold and the book is flat, buy with position_pct of cash.",
            "If RSI > sell_threshold and a long is held, sell all.",
            "No shorting. Neutral RSI is a hold.",
        ],
        "parameters": _params(RSIMeanReversionStrategy),
        "universe": None,
        "score_weights": None,
    }


def _theme_entry() -> dict[str, Any]:
    return {
        "id": "theme_rotation",
        "name": "HK Tech Theme Rotation",
        "class_name": ThemeRotationStrategy.__name__,
        "markets": ["hk"],
        "horizon": "Monthly, multi-asset",
        "summary": inspect.getdoc(ThemeRotationStrategy) or "",
        "thesis": (
            "Long-horizon Hang Seng TECH / Chinese-internet allocation. Capital rotates "
            "across platforms, hardware, semis, and EV — not finance/property and not "
            "intraday. Composite score mixes supply-demand, the policy calendar, and "
            "international macros."
        ),
        "rules": [
            "Rebalance on the last HK session of each month.",
            "Score = demand + policy + international (weights below), each clipped to [-2, 2].",
            "If the best theme score is below cash_threshold, invest only risk_off_invested and hold the rest in cash.",
            "Otherwise softmax theme scores into weights; equal-weight when the score range is inside equal_weight_band.",
            "Spread each theme's weight equally across members that have a quote that day.",
        ],
        "parameters": _params(ThemeRotationStrategy, skip=frozenset({"scores", "themes"})),
        "universe": _theme_universe(),
        "score_weights": {
            "demand": DEMAND_WEIGHT,
            "policy": POLICY_WEIGHT,
            "international": INTL_WEIGHT,
        },
    }


_BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "ma_crossover": _ma_entry,
    "rsi_mean_reversion": _rsi_entry,
    "theme_rotation": _theme_entry,
}


def list_strategies(market: str | None = None) -> list[dict[str, Any]]:
    """Return catalog entries, optionally filtered by market id."""
    entries = [builder() for builder in _BUILDERS.values()]
    if market:
        entries = [e for e in entries if market in e["markets"]]
    return entries


def get_strategy(strategy_id: str) -> dict[str, Any] | None:
    builder = _BUILDERS.get(strategy_id)
    return builder() if builder else None
