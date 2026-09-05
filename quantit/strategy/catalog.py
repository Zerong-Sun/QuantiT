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
from quantit.markets.cn import CN_ETF_NAMES, CN_ETF_THEMES, CN_STOCK_UNIVERSE
from quantit.markets.hk import HK_NAMES, HSTECH_THEMES
from quantit.research.universes import CN_QUALITY, HK_QUALITY
from quantit.strategy.cn_book import CNQualityBookStrategy
from quantit.strategy.hk_book import HKQualityBookStrategy
from quantit.strategy.regime import ThemeRotationStrategy
from quantit.strategy.technical import MACrossoverStrategy, RSIMeanReversionStrategy
from quantit.strategy.tsmom import TSMOMStrategy

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
    "lookback": "Return lookback in bars (252 ≈ 12 months).",
    "skip": "Skip the most recent bars to avoid 1-month reversal.",
    "target_vol": "Annualized volatility target; quality books shrink the sleeve only (no leverage).",
    "vol_lookback": "Bars used to estimate realized volatility.",
    "vol_floor": "Minimum realized vol so size cannot explode.",
    "max_position_pct": "Cap on equity deployed in the name.",
    "rebalance_band": "Ignore size changes smaller than this fraction of the current position.",
    "risk_off_scale": "When momentum is off, hold this fraction of the risk-on sleeve.",
    "invested_on": "Equity fraction in the book when basket momentum is positive.",
    "weighting": "Inside the sleeve: inv_vol (vol-parity) or equal (1/n).",
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


def _cn_etf_universe() -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for theme, members in CN_ETF_THEMES.items():
        out[theme] = [{"symbol": s, "name": CN_ETF_NAMES.get(s, s)} for s in members]
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
            "If SMA(fast) is above SMA(slow) and the book is flat, buy with position_pct of cash (cross or already-in-trend).",
            "If SMA(fast) crosses below SMA(slow) and a long is held, sell all.",
            "When the trend is down, this card yields to RSI mean reversion so the two rules do not share a slot.",
            "Paper fills at the delayed last print. Backtests still fill on the next bar's open unless configured otherwise.",
            "Paper runner also buys a 21–90 DTE ATM call overlay (~5% of US seed) on a buy, and closes those calls on a sell.",
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
            "Mean reversion, armed only when the 10/30 SMA trend is down. RSI below "
            "the buy threshold is treated as short-term oversold; above the sell "
            "threshold as overbought. Ignored in an uptrend so it cannot fight MA."
        ),
        "rules": [
            "Only when SMA(fast) <= SMA(slow): if RSI < buy_threshold and the book is flat, buy.",
            "Only when SMA(fast) <= SMA(slow): if RSI > sell_threshold and a long is held, sell all.",
            "No shorting. Neutral RSI is a hold. Death-cross MA exits still win over an RSI buy.",
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
        "horizon": "Daily, multi-asset",
        "summary": inspect.getdoc(ThemeRotationStrategy) or "",
        "thesis": (
            "Long-horizon Hang Seng TECH / Chinese-internet allocation. Capital rotates "
            "across platforms, hardware, semis, and EV — not finance/property and not "
            "intraday. Composite score mixes supply-demand, the policy calendar, and "
            "international macros."
        ),
        "rules": [
            "Rebalance each session (paper: at most once per calendar day). Skip a name if the qty change vs current is within turnover_band.",
            "Score = demand + policy + international (weights below), each clipped to [-2, 2].",
            "If the best theme score is below cash_threshold, invest only risk_off_invested and hold the rest in cash.",
            "Otherwise softmax theme scores into weights; equal-weight when the score range is inside equal_weight_band.",
            "Spread each theme's weight equally across members that have a quote that day.",
            "If a name cannot fill one board lot at this book size, its weight goes to 3033.HK (Hang Seng TECH ETF) or stays cash.",
            "Separately, the paper runner applies the same daily trend/RSI book to a 5-digit warrant/CBBC watchlist (~5% of HK seed per name).",
        ],
        "parameters": _params(ThemeRotationStrategy, skip=frozenset({"scores", "themes"})),
        "universe": _theme_universe(),
        "score_weights": {
            "demand": DEMAND_WEIGHT,
            "policy": POLICY_WEIGHT,
            "international": INTL_WEIGHT,
        },
    }


def _hk_quality_universe() -> dict[str, list[dict[str, str]]]:
    return {
        "quality": [{"symbol": s, "name": HK_NAMES.get(s, s)} for s in HK_QUALITY],
    }


def _cn_quality_universe() -> dict[str, list[dict[str, str]]]:
    return {
        "quality": [{"symbol": s, "name": CN_STOCK_UNIVERSE.get(s, s)} for s in CN_QUALITY],
    }


def _hk_quality_entry() -> dict[str, Any]:
    return {
        "id": "hk_quality_book",
        "name": "HK Quality Basket TSMOM",
        "class_name": HKQualityBookStrategy.__name__,
        "markets": ["hk"],
        "horizon": "Daily, multi-asset",
        "summary": inspect.getdoc(HKQualityBookStrategy) or "",
        "thesis": (
            "One time-series momentum signal on an equal-weight book of operating "
            "Hong Kong blue chips (grid, bank, insurance, exchange, industrials). "
            "Not Hang Seng TECH rotation. Price only — quality labels pick the pool."
        ),
        "rules": [
            "Rebalance each session (paper: at most once per calendar day). Skip a name if the qty change vs current is within turnover_band.",
            "Momentum = skipped lookback return of the equal-weight close index.",
            "If momentum > 0, invest invested_on, then shrink by vol_scale vs target_vol (never lever).",
            "If momentum ≤ 0, invest risk_off_scale (0 means cash), then apply the same vol_scale.",
            "Split the sleeve by inverse-vol (weighting=equal for 1/n). Names that cannot fill one board lot stay out; residual is cash, not 3033.HK.",
            "Paper runner uses this card only after a walk-forward promote with hk_primary: hk_quality_book.",
        ],
        "parameters": _params(HKQualityBookStrategy, skip=frozenset({"universe"})),
        "universe": _hk_quality_universe(),
        "score_weights": None,
    }


def _cn_quality_entry() -> dict[str, Any]:
    return {
        "id": "cn_quality_book",
        "name": "CN Quality Basket TSMOM",
        "class_name": CNQualityBookStrategy.__name__,
        "markets": ["cn"],
        "horizon": "Daily, multi-asset",
        "summary": inspect.getdoc(CNQualityBookStrategy) or "",
        "thesis": (
            "One time-series momentum signal on an equal-weight book of operating "
            "A-share blue chips (appliance, pharma, power, bank, insurance, consumer). "
            "Not industry-ETF rotation. Price only — quality labels pick the pool."
        ),
        "rules": [
            "Rebalance each session (paper: at most once per calendar day). Skip a name if the qty change vs current is within turnover_band.",
            "Momentum = skipped lookback return of the equal-weight close index.",
            "If momentum > 0, invest invested_on, then shrink by vol_scale vs target_vol (never lever). CN default target_vol is 0.30.",
            "If momentum ≤ 0, invest risk_off_scale (0 means cash), then apply the same vol_scale. Do not raise risk_off_scale.",
            "Split the sleeve by inverse-vol (weighting=equal for 1/n). Names that cannot fill one 100-share lot stay out; residual is cash, not 510300.SS.",
            "Paper runner uses this card only after a walk-forward promote with cn_primary: cn_quality_book.",
        ],
        "parameters": _params(CNQualityBookStrategy, skip=frozenset({"universe"})),
        "universe": _cn_quality_universe(),
        "score_weights": None,
    }


def _cn_etf_entry() -> dict[str, Any]:
    return {
        "id": "cn_etf_rotation",
        "name": "CN Industry ETF Rotation",
        "class_name": ThemeRotationStrategy.__name__,
        "markets": ["cn"],
        "horizon": "Daily, multi-asset",
        "summary": (
            "Allocate onshore A-share industry ETFs from precomputed regime scores. "
            "Rebalances each session; turnover_band skips tiny quantity changes."
        ),
        "thesis": (
            "Long-horizon onshore industry-ETF allocation. Capital rotates across "
            "semiconductors, new energy / NEV, healthcare, and defense — not single-name "
            "A-shares and not intraday. Composite score mixes ETF demand versus CSI 300, "
            "an industrial-policy calendar, and international macros."
        ),
        "rules": [
            "Rebalance each session (paper: at most once per calendar day). Skip a name if the qty change vs current is within turnover_band.",
            "Score = demand + policy + international (weights below), each clipped to [-2, 2].",
            "Demand is theme relative volume plus cumulative return versus 510300.SS.",
            "If the best theme score is below cash_threshold, invest only risk_off_invested and hold the rest in cash.",
            "Otherwise softmax theme scores into weights; equal-weight when the score range is inside equal_weight_band.",
            "Spread each theme's weight equally across members that have a quote that day.",
            "If a name cannot fill one 100-share lot at this book size, its weight goes to 510300.SS (CSI 300 ETF) or stays cash.",
            "Onshore ETFs are stamp-duty exempt; T+1 still applies.",
        ],
        "parameters": _params(ThemeRotationStrategy, skip=frozenset({"scores", "themes"})),
        "universe": _cn_etf_universe(),
        "score_weights": {
            "demand": DEMAND_WEIGHT,
            "policy": POLICY_WEIGHT,
            "international": INTL_WEIGHT,
        },
    }


def _tsmom_entry() -> dict[str, Any]:
    return {
        "id": "tsmom",
        "name": "Time-Series Momentum",
        "class_name": TSMOMStrategy.__name__,
        "markets": ["us"],
        "horizon": "Daily, single-name",
        "summary": inspect.getdoc(TSMOMStrategy) or "",
        "thesis": (
            "Own-price trend. The sign of the skipped 12-month return decides whether "
            "to hold the name; position size targets a constant annualized volatility. "
            "Cash when momentum is non-positive. No shorting."
        ),
        "rules": [
            "Momentum = close[t-skip] / close[t-lookback] - 1 (default skip 21, lookback 252).",
            "If momentum > 0, size so notional vol ≈ target_vol, capped by max_position_pct.",
            "If momentum ≤ 0, sell all and stay cash.",
            "Resize when the target quantity moves by more than rebalance_band.",
            "Paper runner uses this card only after a walk-forward promote with us_primary: tsmom.",
        ],
        "parameters": _params(TSMOMStrategy),
        "universe": None,
        "score_weights": None,
    }


_BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "ma_crossover": _ma_entry,
    "rsi_mean_reversion": _rsi_entry,
    "tsmom": _tsmom_entry,
    "hk_quality_book": _hk_quality_entry,
    "cn_quality_book": _cn_quality_entry,
    "theme_rotation": _theme_entry,
    "cn_etf_rotation": _cn_etf_entry,
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
