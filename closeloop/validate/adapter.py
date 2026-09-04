"""Alphalens-style factor + forward returns. Uses alphalens-reloaded when installed."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from closeloop.data.protocol import field_frame
from closeloop.factors.ops import factor_stack


@dataclass
class CleanFactor:
    """Aligned factor, forward returns, and quantile labels."""

    data: pd.DataFrame
    periods: tuple[int, ...]


def _stack_factor(factor: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(factor, pd.DataFrame):
        series = factor_stack(factor)
    else:
        series = factor.copy()
        series.index.names = ["date", "asset"]
    series.name = "factor"
    return series


def _forward_returns(prices: pd.DataFrame, periods: tuple[int, ...]) -> pd.DataFrame:
    frames = []
    for p in periods:
        ret = prices.shift(-p) / prices - 1.0
        col = factor_stack(ret)
        col.name = p
        frames.append(col)
    return pd.concat(frames, axis=1)


def _assign_quantiles(frame: pd.DataFrame, quantiles: int) -> pd.Series:
    def _qcut(s: pd.Series) -> pd.Series:
        valid = s.dropna()
        if valid.nunique() < 2:
            return pd.Series(index=s.index, dtype=float)
        try:
            labels = pd.qcut(valid, quantiles, labels=False, duplicates="drop") + 1
        except ValueError:
            return pd.Series(index=s.index, dtype=float)
        out = pd.Series(index=s.index, dtype=float)
        out.loc[labels.index] = labels.astype(float)
        return out

    grouped = frame.groupby(level="date")["factor"]
    return grouped.transform(_qcut)


def _builtin_clean(
    factor: pd.Series | pd.DataFrame,
    prices: pd.DataFrame,
    periods: tuple[int, ...],
    quantiles: int,
) -> CleanFactor:
    fac = _stack_factor(factor)
    fwd = _forward_returns(prices, periods)
    data = pd.concat([fac, fwd], axis=1).dropna(subset=["factor"])
    data["factor_quantile"] = _assign_quantiles(data, quantiles)
    data = data.dropna(subset=list(periods), how="all")
    data.index.names = ["date", "asset"]
    return CleanFactor(data=data, periods=periods)


def _alphalens_clean(
    factor: pd.Series | pd.DataFrame,
    prices: pd.DataFrame,
    periods: tuple[int, ...],
    quantiles: int,
) -> CleanFactor | None:
    try:
        from alphalens.utils import get_clean_factor_and_forward_returns
    except ImportError:
        return None
    fac = _stack_factor(factor)
    fac.index = fac.index.set_names(["date", "asset"])
    px = prices.copy()
    px.index = pd.DatetimeIndex(px.index)
    try:
        raw = get_clean_factor_and_forward_returns(
            fac,
            px,
            periods=list(periods),
            quantiles=quantiles,
            max_loss=0.35,
        )
    except Exception:
        return None
    rename = {}
    for p in periods:
        for cand in (p, f"{p}D", f"{p}D"):
            if cand in raw.columns:
                rename[cand] = p
                break
    data = raw.rename(columns=rename)
    keep = ["factor", "factor_quantile", *[c for c in periods if c in data.columns]]
    data = data.loc[:, [c for c in keep if c in data.columns]]
    data.index.names = ["date", "asset"]
    return CleanFactor(data=data, periods=periods)


def get_clean_factor_and_forward_returns(
    factor: pd.Series | pd.DataFrame,
    prices: pd.DataFrame,
    periods: tuple[int, ...] = (1, 5, 10),
    quantiles: int = 5,
) -> CleanFactor:
    al = _alphalens_clean(factor, prices, periods, quantiles)
    if al is not None:
        return al
    return _builtin_clean(factor, prices, periods, quantiles)


def prices_from_panel(panel: pd.DataFrame) -> pd.DataFrame:
    return field_frame(panel, "close")
