"""Grid search over a single data window."""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantit.analysis.metrics import compute_metrics
from quantit.engine.backtester import Backtester
from quantit.engine.broker import Order
from quantit.research.specs import get_spec
from quantit.strategy.base import Context, Strategy


class BuyAndHoldStrategy(Strategy):
    """Buy once with most of the cash and hold."""

    def __init__(self, position_pct: float = 0.95) -> None:
        self.position_pct = position_pct
        self._bought = False

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if self._bought or context.position > 0:
            return
        context.buy_pct(self.position_pct)
        self._bought = True


class EqualWeightHold(Strategy):
    """Split cash equally across names on the first bar and hold."""

    def __init__(self, position_pct: float = 0.95) -> None:
        self.position_pct = position_pct
        self._bought = False

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if self._bought:
            return
        names = list(context.data_map) if context.data_map else [context.symbol]
        n = len(names)
        if n == 0:
            self._bought = True
            return
        cash = float(context.portfolio.cash) * self.position_pct
        budget = cash / n
        for sym in names:
            px = (context.prices or {}).get(sym)
            if px is None or px <= 0:
                continue
            qty = int(budget / px)
            if qty > 0:
                context.buy(qty, symbol=sym)
        self._bought = True


class DelayedStart(Strategy):
    """Compute indicators on the full frame, but do not trade before ``active_from``."""

    def __init__(self, inner: Strategy, active_from: object) -> None:
        self.inner = inner
        self.active_from = pd.Timestamp(active_from)

    def on_start(self, context: Context) -> None:
        self.inner.on_start(context)

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if context.current_date is None or pd.Timestamp(context.current_date) < self.active_from:
            return
        self.inner.on_bar(context, bar)

    def on_order(self, context: Context, order: Order) -> None:
        self.inner.on_order(context, order)

    def on_end(self, context: Context) -> None:
        self.inner.on_end(context)


def calendar_index(data: pd.DataFrame | dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """Union of session dates (sorted, unique). Empty input → empty index."""
    if isinstance(data, dict):
        idx: pd.Index | None = None
        for df in data.values():
            if df is None or getattr(df, "empty", True):
                continue
            idx = df.index if idx is None else idx.union(df.index)
        if idx is None:
            return pd.DatetimeIndex([])
        return pd.DatetimeIndex(idx).sort_values().unique()
    if data is None or getattr(data, "empty", True):
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(data.index).sort_values().unique()


def slice_by_dates(
    data: pd.DataFrame | dict[str, pd.DataFrame],
    dates: pd.Index,
) -> pd.DataFrame | dict[str, pd.DataFrame]:
    """Keep rows whose index is in ``dates`` (calendar alignment, not iloc)."""
    wanted = pd.DatetimeIndex(dates)
    if isinstance(data, dict):
        out: dict[str, pd.DataFrame] = {}
        for sym, df in data.items():
            if df is None or getattr(df, "empty", True):
                continue
            part = df.loc[df.index.intersection(wanted)]
            if not part.empty:
                out[sym] = part
        return out
    return data.loc[data.index.intersection(wanted)]


def _is_empty(data: pd.DataFrame | dict[str, pd.DataFrame] | None) -> bool:
    if data is None:
        return True
    if isinstance(data, dict):
        return not data or all(df is None or getattr(df, "empty", True) for df in data.values())
    return bool(getattr(data, "empty", True))


def run_backtest(
    strategy_id: str,
    params: dict[str, Any],
    data: pd.DataFrame | dict[str, pd.DataFrame],
    symbol: str,
    initial_cash: float = 100_000.0,
    extra: dict[str, Any] | None = None,
    metric_start: object | None = None,
    metric_end: object | None = None,
    active_from: object | None = None,
) -> dict[str, Any]:
    spec = get_spec(strategy_id)
    if spec.kind == "multi":
        scores = (extra or {}).get("scores")
        if scores is None:
            raise ValueError("theme_rotation research requires extra['scores']")
        strategy: Strategy = spec.builder(scores, **params)
    else:
        strategy = spec.builder(**params)
    if active_from is not None:
        strategy = DelayedStart(strategy, active_from)
    result = Backtester(initial_cash=initial_cash).run(strategy, data, symbol=symbol)
    start = pd.Timestamp(metric_start).to_pydatetime() if metric_start is not None else None
    end = pd.Timestamp(metric_end).to_pydatetime() if metric_end is not None else None
    metrics = compute_metrics(result, start=start, end=end)
    return {"params": params, "metrics": metrics, "result": result}


def buy_and_hold_metrics(
    data: pd.DataFrame | dict[str, pd.DataFrame],
    symbol: str,
    initial_cash: float = 100_000.0,
) -> dict[str, float]:
    if isinstance(data, dict):
        result = Backtester(initial_cash=initial_cash).run(
            EqualWeightHold(), data, symbol=symbol
        )
    else:
        result = Backtester(initial_cash=initial_cash).run(
            BuyAndHoldStrategy(), data, symbol=symbol
        )
    return compute_metrics(result)


def grid_search(
    strategy_id: str,
    data: pd.DataFrame | dict[str, pd.DataFrame],
    symbol: str,
    grid: list[dict[str, Any]] | None = None,
    initial_cash: float = 100_000.0,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = get_spec(strategy_id)
    combos = grid if grid is not None else spec.grid
    if not combos:
        raise ValueError(f"No parameter grid for {strategy_id}")
    ranked: list[dict[str, Any]] = []
    for params in combos:
        ranked.append(run_backtest(strategy_id, params, data, symbol, initial_cash, extra))
    ranked.sort(
        key=lambda row: (
            float(row["metrics"].get("sharpe_ratio") or 0.0),
            -abs(float(row["metrics"].get("max_drawdown") or 0.0)),
        ),
        reverse=True,
    )
    return ranked[0]
