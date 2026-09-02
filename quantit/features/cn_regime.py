"""A-share industry-ETF demand scores (volume + excess vs CSI 300)."""

from __future__ import annotations

import pandas as pd

from quantit.features.regime import (
    DEMAND_WEIGHT,
    INTL_WEIGHT,
    POLICY_WEIGHT,
    _weighted_z,
    international_score,
    rolling_zscore,
    theme_equal_weight_return,
    theme_relative_volume,
)
from quantit.markets.cn import CN_ETF_FALLBACK, CN_ETF_THEMES
from quantit.policy.calendar import PolicyCalendar


def cn_demand_score(
    ohlcv: dict[str, pd.DataFrame],
    themes: dict[str, list[str]],
    macros: pd.DataFrame,
    benchmark: str = CN_ETF_FALLBACK,
    lookback: int = 60,
) -> pd.DataFrame:
    """Theme demand: relative volume plus cumulative return vs CSI 300."""
    bench_ret = theme_equal_weight_return(ohlcv, [benchmark])
    if bench_ret.empty:
        all_members = [s for members in themes.values() for s in members]
        bench_ret = theme_equal_weight_return(ohlcv, all_members)
    bench_cum = bench_ret.rolling(lookback, min_periods=max(10, lookback // 4)).sum()

    fx = pd.Series(dtype=float)
    if macros is not None and not macros.empty and "cny" in macros.columns:
        fx = rolling_zscore(macros["cny"].pct_change(lookback))

    columns: dict[str, pd.Series] = {}
    for name, members in themes.items():
        rv = theme_relative_volume(ohlcv, members, window=lookback)
        theme_ret = theme_equal_weight_return(ohlcv, members)
        theme_cum = theme_ret.rolling(lookback, min_periods=max(10, lookback // 4)).sum()
        excess = (theme_cum - bench_cum).reindex(theme_cum.index.union(bench_cum.index)).sort_index()
        excess = excess.ffill()
        parts = [
            (0.6, rolling_zscore(rv)),
            (0.4, rolling_zscore(excess)),
            (-0.3, fx if not fx.empty else pd.Series(dtype=float)),
        ]
        columns[name] = _weighted_z(parts).clip(-2, 2)
    return pd.DataFrame(columns)


def compute_cn_etf_scores(
    ohlcv: dict[str, pd.DataFrame],
    macros: pd.DataFrame,
    calendar: PolicyCalendar | None = None,
    themes: dict[str, list[str]] | None = None,
    demand_weight: float = DEMAND_WEIGHT,
    policy_weight: float = POLICY_WEIGHT,
    intl_weight: float = INTL_WEIGHT,
    benchmark: str = CN_ETF_FALLBACK,
) -> pd.DataFrame:
    """Daily CN ETF theme scores in [-2, 2] after mixing demand, policy, and international."""
    themes = themes or CN_ETF_THEMES
    calendar = calendar or PolicyCalendar.load_cn()

    idx_parts = [df.index for df in ohlcv.values() if df is not None and not df.empty]
    if not idx_parts:
        return pd.DataFrame(columns=list(themes.keys()))
    calendar_index = pd.DatetimeIndex(pd.to_datetime(idx_parts[0])).normalize()
    for extra in idx_parts[1:]:
        calendar_index = calendar_index.union(pd.DatetimeIndex(pd.to_datetime(extra)).normalize())
    calendar_index = calendar_index.sort_values()

    demand = cn_demand_score(ohlcv, themes, macros, benchmark=benchmark)
    policy = calendar.series(calendar_index)
    intl = international_score(macros)

    demand = demand.reindex(calendar_index).ffill()
    policy = policy.reindex(calendar_index).ffill()
    intl = intl.reindex(calendar_index).ffill()

    scores = pd.DataFrame(index=calendar_index)
    for theme in themes:
        d = demand[theme] if theme in demand.columns else pd.Series(0.0, index=calendar_index)
        p = policy[theme] if theme in policy.columns else pd.Series(0.0, index=calendar_index)
        scores[theme] = (
            demand_weight * d.fillna(0.0)
            + policy_weight * p.fillna(0.0)
            + intl_weight * intl.fillna(0.0)
        ).clip(-2, 2)
    return scores
