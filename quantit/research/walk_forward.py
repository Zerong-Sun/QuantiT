"""Rolling walk-forward study."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import math

import pandas as pd

from quantit.research.gates import GateResult, evaluate_gates, evaluate_promote_gates, fold_regime
from quantit.research.search import (
    _is_empty,
    buy_and_hold_metrics,
    calendar_index,
    grid_search,
    run_backtest,
    slice_by_dates,
)
from quantit.research.specs import get_spec

__all__ = [
    "FoldResult",
    "StudyResult",
    "calendar_index",
    "iter_folds",
    "walk_forward",
]


@dataclass
class FoldResult:
    train: slice
    test: slice
    params: dict[str, Any]
    is_metrics: dict[str, float]
    oos_metrics: dict[str, float]
    bh_metrics: dict[str, float]
    us_book_metrics: dict[str, float] = field(default_factory=dict)
    test_start: str = ""
    test_end: str = ""
    regime: str = ""


@dataclass
class StudyResult:
    strategy_id: str
    symbol: str
    folds: list[FoldResult] = field(default_factory=list)
    oos_sharpe: float = 0.0
    oos_drawdown: float = 0.0
    oos_trades: float = 0.0
    bh_sharpe: float = 0.0
    bh_drawdown: float = 0.0
    best_params: dict[str, Any] = field(default_factory=dict)
    gate: GateResult | None = None
    promote_gate: GateResult | None = None

    @property
    def passed(self) -> bool:
        return bool(self.gate and self.gate.passed)


def iter_folds(n: int, train: int = 504, test: int = 126, step: int = 126) -> list[tuple[slice, slice]]:
    folds: list[tuple[slice, slice]] = []
    start = 0
    while start + train + test <= n:
        folds.append((slice(start, start + train), slice(start + train, start + train + test)))
        start += step
    return folds


def _mean(values: list[float]) -> float:
    finite = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not finite:
        return 0.0
    return float(sum(finite) / len(finite))


def walk_forward(
    strategy_id: str,
    data: pd.DataFrame | dict[str, pd.DataFrame],
    symbol: str = "STUDY",
    train: int = 504,
    test: int = 126,
    step: int = 126,
    grid: list[dict[str, Any]] | None = None,
    initial_cash: float = 100_000.0,
    extra: dict[str, Any] | None = None,
) -> StudyResult:
    get_spec(strategy_id)
    cal = calendar_index(data)
    n = len(cal)
    study = StudyResult(strategy_id=strategy_id, symbol=symbol)
    for train_sl, test_sl in iter_folds(n, train=train, test=test, step=step):
        train_dates = cal[train_sl]
        test_dates = cal[test_sl]
        eval_dates = cal[slice(train_sl.start, test_sl.stop)]
        train_data = slice_by_dates(data, train_dates)
        test_data = slice_by_dates(data, test_dates)
        eval_data = slice_by_dates(data, eval_dates)
        extra_train = _slice_extra_by_dates(extra, train_dates)
        extra_eval = _slice_extra_by_dates(extra, eval_dates)
        if _is_empty(train_data) or _is_empty(test_data):
            continue
        test_start = test_dates[0]
        test_end = test_dates[-1]
        try:
            best = grid_search(
                strategy_id, train_data, symbol, grid=grid, initial_cash=initial_cash, extra=extra_train
            )
            # Replay train+test so lookback indicators are warm; score only the OOS window.
            oos = run_backtest(
                strategy_id,
                best["params"],
                eval_data,
                symbol,
                initial_cash,
                extra_eval,
                metric_start=test_start,
                metric_end=test_end,
                active_from=test_start,
            )
            bh = buy_and_hold_metrics(test_data, symbol, initial_cash)
        except (ValueError, KeyError):
            continue
        ub_metrics: dict[str, float] = {}
        if strategy_id == "tsmom":
            try:
                ub = run_backtest(
                    "us_book",
                    {},
                    eval_data,
                    symbol,
                    initial_cash,
                    metric_start=test_start,
                    metric_end=test_end,
                    active_from=test_start,
                )
                ub_metrics = ub["metrics"]
            except (ValueError, KeyError):
                ub_metrics = {}
        bh_sharpe = float(bh.get("sharpe_ratio") or 0.0)
        study.folds.append(
            FoldResult(
                train=train_sl,
                test=test_sl,
                params=best["params"],
                is_metrics=best["metrics"],
                oos_metrics=oos["metrics"],
                bh_metrics=bh,
                us_book_metrics=ub_metrics,
                test_start=str(pd.Timestamp(test_dates[0]).date()),
                test_end=str(pd.Timestamp(test_dates[-1]).date()),
                regime=fold_regime(bh_sharpe),
            )
        )
    if not study.folds:
        study.gate = GateResult(passed=False, reasons=("Not enough bars for walk-forward folds",))
        study.promote_gate = study.gate
        return study
    study.oos_sharpe = _mean([float(f.oos_metrics.get("sharpe_ratio") or 0.0) for f in study.folds])
    study.oos_drawdown = min(float(f.oos_metrics.get("max_drawdown") or 0.0) for f in study.folds)
    study.oos_trades = sum(float(f.oos_metrics.get("total_trades") or 0.0) for f in study.folds)
    study.bh_sharpe = _mean([float(f.bh_metrics.get("sharpe_ratio") or 0.0) for f in study.folds])
    study.bh_drawdown = min(float(f.bh_metrics.get("max_drawdown") or 0.0) for f in study.folds)
    study.best_params = dict(study.folds[-1].params)
    study.gate = evaluate_gates(
        oos_sharpe=study.oos_sharpe,
        oos_drawdown=study.oos_drawdown,
        oos_trades=study.oos_trades,
        buy_hold_sharpe=study.bh_sharpe,
        buy_hold_drawdown=study.bh_drawdown,
    )
    study.promote_gate = evaluate_promote_gates(
        oos_sharpe=study.oos_sharpe,
        oos_drawdown=study.oos_drawdown,
        oos_trades=study.oos_trades,
        buy_hold_sharpe=study.bh_sharpe,
        buy_hold_drawdown=study.bh_drawdown,
        folds=study.folds,
    )
    return study


def _slice_extra_by_dates(extra: dict[str, Any] | None, dates: pd.Index) -> dict[str, Any] | None:
    if not extra:
        return extra
    out = dict(extra)
    scores = extra.get("scores")
    if scores is not None and hasattr(scores, "loc"):
        out["scores"] = slice_by_dates(scores, dates)
    return out
