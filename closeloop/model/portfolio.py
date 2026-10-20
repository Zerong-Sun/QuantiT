"""Daily close execution proxy for independent, long-only research portfolios.

Signals must already be delayed to their availability date. Fractional positions,
fixed-universe history and approximate trading limits prevent live promotion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PortfolioConfig:
    top_k: int = 20
    rebalance: int = 5
    turnover_limit: float = 0.4  # sum(abs(buys), abs(sells)) / equity per rebalance
    buy_cost: float = 0.0015  # commission + slippage assumption
    sell_cost: float = 0.0020  # commission + slippage + tax assumption
    limit_threshold: float = 0.095

    def __post_init__(self):
        if self.top_k < 1 or self.rebalance < 1:
            raise ValueError("top_k and rebalance must be positive")
        if not 0 < self.turnover_limit <= 2:
            raise ValueError("turnover_limit must be in (0, 2]")
        if not 0 <= self.buy_cost < 1 or not 0 <= self.sell_cost < 1:
            raise ValueError("costs must be in [0, 1)")
        if not 0 < self.limit_threshold < 1:
            raise ValueError("limit_threshold must be in (0, 1)")


def performance(curve: pd.DataFrame) -> dict:
    if curve.empty:
        return {"sessions": 0, "net_return": None, "annual_return": None,
                "sharpe": None, "max_drawdown": None}
    returns = curve["net_return"].astype(float)
    nav = (1 + returns).cumprod()
    peak = np.maximum.accumulate(np.r_[1.0, nav.to_numpy()])[1:]
    std = float(returns.std(ddof=0))
    return {
        "sessions": len(curve), "net_return": float(nav.iloc[-1] - 1),
        "annual_return": float(nav.iloc[-1] ** (252 / len(curve)) - 1),
        "sharpe": float(returns.mean() / std * np.sqrt(252)) if std > 0 else None,
        "max_drawdown": float((nav.to_numpy() / peak - 1).min()),
        "mean_turnover": float(curve["turnover"].mean()),
        "cost_sum": float(curve["cost"].sum()),
        "stale_valuation_sessions": int(curve["stale_valuation"].sum()),
    }


def simulate(
    scores: pd.DataFrame, close: pd.DataFrame, volume: pd.DataFrame,
    config: PortfolioConfig, *, start: pd.Timestamp, end: pd.Timestamp,
) -> pd.DataFrame:
    """Trade at t close using lagged signals, earn t→t+1, label the row t.

    Missing marks are carried forward only for valuation, flagged in the output,
    and never used to authorize fills. Last date without a following mark is not
    scored. Turnover includes both sides; costs are charged on executed changes.
    """
    if close.index.has_duplicates or not close.index.is_monotonic_increasing:
        raise ValueError("close calendar must be unique and sorted")
    if not np.isfinite(close.to_numpy(dtype=float)[close.notna().to_numpy()]).all():
        raise ValueError("nonfinite close prices")
    close = close.where(close > 0)
    marks = close.ffill()
    volume = volume.reindex_like(close)
    scores = scores.reindex(index=close.index, columns=close.columns).replace([np.inf, -np.inf], np.nan)
    dates = close.index[(close.index >= start) & (close.index <= end)]
    dates = dates.intersection(close.index[:-1])
    if len(dates) and not dates.equals(close.index[close.index.get_loc(dates[0]):close.index.get_loc(dates[-1]) + 1]):
        raise ValueError("evaluation dates must be contiguous")
    weights = np.zeros(len(close.columns))
    rows = []
    raw = close.to_numpy(dtype=float)
    mark = marks.to_numpy(dtype=float)
    vols = volume.to_numpy(dtype=float)
    score_values = scores.to_numpy(dtype=float)
    for step, day in enumerate(dates):
        i = close.index.get_loc(day)
        previous = raw[i - 1] if i else np.full(len(weights), np.nan)
        change = np.divide(raw[i], previous, out=np.ones(len(weights)), where=previous > 0) - 1
        tradable = np.isfinite(raw[i]) & (vols[i] > 0) & np.isfinite(previous)
        # Both directions blocked at extreme daily moves: conservative daily-bar proxy.
        tradable &= np.abs(change) < config.limit_threshold
        delta = np.zeros_like(weights)
        if step % config.rebalance == 0:
            eligible = tradable & np.isfinite(score_values[i])
            ranked = np.flatnonzero(eligible)
            ranked = ranked[np.argsort(-score_values[i, ranked], kind="stable")][:config.top_k]
            target = weights.copy()
            target[tradable] = 0
            budget = max(0.0, 1 - target.sum())
            target[ranked] = min(1 / config.top_k, budget / len(ranked)) if len(ranked) else 0
            delta = target - weights
            amount = np.abs(delta).sum()
            if amount > config.turnover_limit:
                delta *= config.turnover_limit / amount
            sell = -np.minimum(delta, 0).sum()
            buy = np.maximum(delta, 0).sum()
            cash = max(0.0, 1 - weights.sum())
            affordable = max(0.0, (cash + sell * (1 - config.sell_cost)) / (1 + config.buy_cost))
            if buy > affordable:
                delta[delta > 0] *= affordable / buy
        fee = float(np.maximum(delta, 0).sum() * config.buy_cost
                    - np.minimum(delta, 0).sum() * config.sell_cost)
        held = weights + delta
        returns = np.divide(mark[i + 1], mark[i], out=np.ones(len(weights)), where=mark[i] > 0) - 1
        returns = np.nan_to_num(returns, nan=0.0)
        stale = bool(np.any((held > 1e-12) & (~np.isfinite(raw[i]) | ~np.isfinite(raw[i + 1]))))
        growth = 1 - fee + float(np.dot(held, returns))
        if not np.isfinite(growth) or growth <= 0:
            raise ValueError("portfolio became insolvent or nonfinite")
        weights = held * (1 + returns) / growth
        rows.append({"date": day, "net_return": growth - 1,
                     "turnover": float(np.abs(delta).sum()), "cost": fee,
                     "stale_valuation": stale, "cash_weight": max(0.0, 1 - weights.sum())})
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame(
        columns=["net_return", "turnover", "cost", "stale_valuation", "cash_weight"])


def config_dict(config: PortfolioConfig) -> dict:
    return asdict(config)
