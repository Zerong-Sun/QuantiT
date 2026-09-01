"""Regime scores: supply-demand, policy calendar, international macros."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quantit.data.macro import load_southbound_csv
from quantit.markets.hk import HSTECH_THEMES
from quantit.policy.calendar import PolicyCalendar

DEMAND_WEIGHT = 0.35
POLICY_WEIGHT = 0.35
INTL_WEIGHT = 0.30


def rolling_zscore(series: pd.Series, window: int = 252, min_periods: int = 40) -> pd.Series:
    """Rolling z-score clipped to [-2, 2]."""
    mu = series.rolling(window, min_periods=min_periods).mean()
    sd = series.rolling(window, min_periods=min_periods).std()
    z = (series - mu) / sd.replace(0, np.nan)
    return z.clip(-2, 2)


def _pct_change(series: pd.Series, periods: int) -> pd.Series:
    return series.pct_change(periods)


def _lookback_change(series: pd.Series, periods: int) -> pd.Series:
    """Absolute change over ``periods`` (for yields)."""
    return series.diff(periods)


def theme_relative_volume(
    ohlcv: dict[str, pd.DataFrame],
    members: list[str],
    window: int = 60,
) -> pd.Series:
    parts: list[pd.Series] = []
    for symbol in members:
        df = ohlcv.get(symbol)
        if df is None or df.empty or "volume" not in df.columns:
            continue
        avg = df["volume"].rolling(window, min_periods=max(10, window // 4)).mean()
        parts.append(df["volume"] / avg.replace(0, np.nan))
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, axis=1).mean(axis=1)


def theme_equal_weight_return(
    ohlcv: dict[str, pd.DataFrame],
    members: list[str],
) -> pd.Series:
    closes: list[pd.Series] = []
    for symbol in members:
        df = ohlcv.get(symbol)
        if df is None or df.empty or "close" not in df.columns:
            continue
        closes.append(df["close"].rename(symbol))
    if not closes:
        return pd.Series(dtype=float)
    panel = pd.concat(closes, axis=1).sort_index()
    return panel.pct_change().mean(axis=1)


def _weighted_z(parts: list[tuple[float, pd.Series]]) -> pd.Series:
    """Weight z-scored series, dropping missing columns and renormalizing weights."""
    usable = [(w, s.dropna()) for w, s in parts if s is not None and not s.empty]
    if not usable:
        return pd.Series(dtype=float)
    aligned = pd.concat([s.rename(str(i)) for i, (_, s) in enumerate(usable)], axis=1)
    weights = np.array([w for w, _ in usable], dtype=float)
    mask = aligned.notna()
    # Per-row renormalize over available factors
    w_row = mask.to_numpy() * weights
    w_sum = w_row.sum(axis=1)
    w_sum = np.where(w_sum <= 0, np.nan, w_sum)
    values = aligned.to_numpy()
    weighted = np.nansum(values * weights, axis=1) / w_sum
    # nansum treats nan as 0; zero-out rows that are all-nan
    all_nan = ~np.any(mask.to_numpy(), axis=1)
    weighted[all_nan] = np.nan
    return pd.Series(weighted, index=aligned.index)


def international_score(macros: pd.DataFrame, lookback: int = 60) -> pd.Series:
    """Shared international factor from DXY, US 10Y, Nasdaq, USDCNY."""
    parts: list[tuple[float, pd.Series]] = []
    if "dxy" in macros.columns:
        parts.append((-0.30, rolling_zscore(_pct_change(macros["dxy"], lookback))))
    if "us10y" in macros.columns:
        parts.append((-0.30, rolling_zscore(_lookback_change(macros["us10y"], lookback))))
    if "nasdaq" in macros.columns:
        parts.append((0.25, rolling_zscore(_pct_change(macros["nasdaq"], lookback))))
    if "cny" in macros.columns:
        parts.append((-0.15, rolling_zscore(_pct_change(macros["cny"], lookback))))
    score = _weighted_z(parts)
    return score.clip(-2, 2)


def demand_score(
    ohlcv: dict[str, pd.DataFrame],
    themes: dict[str, list[str]],
    macros: pd.DataFrame,
    southbound: pd.Series | None = None,
    lookback: int = 60,
) -> pd.DataFrame:
    """Theme-level demand: relative volume, HSTECH vs Nasdaq, FX pressure."""
    all_members = [s for members in themes.values() for s in members]
    hstech_ret = theme_equal_weight_return(ohlcv, all_members)
    hstech_cum_ret = hstech_ret.rolling(lookback, min_periods=max(10, lookback // 4)).sum()

    appetite = pd.Series(dtype=float)
    if "nasdaq" in macros.columns:
        ndq = macros["nasdaq"].pct_change().rolling(lookback, min_periods=max(10, lookback // 4)).sum()
        appetite = (hstech_cum_ret - ndq).reindex(hstech_cum_ret.index.union(ndq.index)).sort_index()
        appetite = appetite.ffill()
    else:
        appetite = hstech_cum_ret

    fx_parts: list[tuple[float, pd.Series]] = []
    if "cny" in macros.columns:
        fx_parts.append((0.7, rolling_zscore(_pct_change(macros["cny"], lookback))))
    if "hkd" in macros.columns:
        peg = (macros["hkd"] - 7.80) / 0.05
        fx_parts.append((0.3, rolling_zscore(peg)))
    fx_pressure = _weighted_z(fx_parts)

    sb_z = pd.Series(dtype=float)
    if southbound is not None and not southbound.empty:
        sb_z = rolling_zscore(southbound.sort_index())

    columns: dict[str, pd.Series] = {}
    for name, members in themes.items():
        rv = theme_relative_volume(ohlcv, members, window=lookback)
        parts = [
            (0.6, rolling_zscore(rv)),
            (0.4, rolling_zscore(appetite)),
            (-0.3, fx_pressure if not fx_pressure.empty else pd.Series(dtype=float)),
        ]
        if not sb_z.empty:
            parts.append((0.3, sb_z))
        columns[name] = _weighted_z(parts).clip(-2, 2)
    return pd.DataFrame(columns)


def compute_theme_scores(
    ohlcv: dict[str, pd.DataFrame],
    macros: pd.DataFrame,
    calendar: PolicyCalendar | None = None,
    themes: dict[str, list[str]] | None = None,
    southbound: pd.Series | str | Path | None = None,
    demand_weight: float = DEMAND_WEIGHT,
    policy_weight: float = POLICY_WEIGHT,
    intl_weight: float = INTL_WEIGHT,
) -> pd.DataFrame:
    """Daily theme scores in [-2, 2] after mixing demand, policy, and international."""
    themes = themes or HSTECH_THEMES
    calendar = calendar or PolicyCalendar.load_default()

    sb: pd.Series | None
    if isinstance(southbound, (str, Path)):
        sb = load_southbound_csv(southbound)
    else:
        sb = southbound

    idx_parts = [df.index for df in ohlcv.values() if df is not None and not df.empty]
    if not idx_parts:
        return pd.DataFrame(columns=list(themes.keys()))
    calendar_index = pd.DatetimeIndex(pd.to_datetime(idx_parts[0])).normalize()
    for extra in idx_parts[1:]:
        calendar_index = calendar_index.union(pd.DatetimeIndex(pd.to_datetime(extra)).normalize())
    calendar_index = calendar_index.sort_values()

    demand = demand_score(ohlcv, themes, macros, southbound=sb)
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


def scores_to_theme_weights(
    scores: dict[str, float],
    cash_threshold: float = -0.5,
    risk_off_invested: float = 0.40,
    equal_weight_band: float = 0.25,
    temperature: float = 1.0,
) -> dict[str, float]:
    """Map theme scores to weights that sum to invested capital (<= 1). Remainder is cash."""
    names = list(scores.keys())
    if not names:
        return {}
    vals = np.array([float(scores[n]) for n in names], dtype=float)
    if np.all(np.isnan(vals)):
        equal = 1.0 / len(names)
        return {n: equal for n in names}

    filled = np.nan_to_num(vals, nan=0.0)
    invested = risk_off_invested if float(np.max(filled)) < cash_threshold else 1.0

    if float(np.max(filled) - np.min(filled)) < equal_weight_band:
        raw = np.ones(len(names), dtype=float) / len(names)
    else:
        ex = np.exp(temperature * np.clip(filled, -2, 2))
        raw = ex / ex.sum()
    return {n: float(invested * w) for n, w in zip(names, raw)}
