"""CLI entry for walk-forward research."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from quantit.paper.capital import US_WATCHLIST
from quantit.research.params import research_dir
from quantit.research.promote import maybe_promote
from quantit.research.report import render_study
from quantit.research.specs import get_spec
from quantit.research.walk_forward import StudyResult, walk_forward


def _combine(studies: list[StudyResult]) -> StudyResult:
    if len(studies) == 1:
        return studies[0]
    base = studies[0]
    n = len(studies)
    last_params = [dict(s.best_params) for s in studies if s.best_params]
    if last_params:
        keys = [json.dumps(p, sort_keys=True, default=str) for p in last_params]
        winner = Counter(keys).most_common(1)[0][0]
        best_params = json.loads(winner)
    else:
        best_params = dict(base.best_params)
    combined = StudyResult(
        strategy_id=base.strategy_id,
        symbol=",".join(s.symbol for s in studies),
        folds=[f for s in studies for f in s.folds],
        oos_sharpe=sum(s.oos_sharpe for s in studies) / n,
        oos_drawdown=min(s.oos_drawdown for s in studies),
        oos_trades=sum(s.oos_trades for s in studies),
        bh_sharpe=sum(s.bh_sharpe for s in studies) / n,
        best_params=best_params,
    )
    from quantit.research.gates import evaluate_gates

    combined.gate = evaluate_gates(
        oos_sharpe=combined.oos_sharpe,
        oos_drawdown=combined.oos_drawdown,
        oos_trades=combined.oos_trades,
        buy_hold_sharpe=combined.bh_sharpe,
    )
    return combined


def _load_us(symbols: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    from quantit.data.loader import DataLoader

    loader = DataLoader()
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        df = loader.load(symbol, start, end)
        if df is not None and not df.empty:
            frames[symbol] = df
    return frames


def _load_hk(start: str, end: str) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    from quantit.data.loader import DataLoader
    from quantit.data.macro import MacroLoader
    from quantit.features.regime import compute_theme_scores
    from quantit.markets.hk import all_hstech_symbols
    from quantit.policy.calendar import PolicyCalendar

    loader = DataLoader()
    ohlcv = loader.load_multi(all_hstech_symbols(), start, end, skip_missing=True)
    calendar = None
    for df in ohlcv.values():
        calendar = df.index if calendar is None else calendar.union(df.index)
    macros = MacroLoader(loader).load(start, end, calendar=calendar, skip_missing=True)
    scores = compute_theme_scores(ohlcv, macros, calendar=PolicyCalendar.load_default())
    return ohlcv, scores


def _load_cn(start: str, end: str) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    from quantit.data.cn_csv import CompositeCNProvider
    from quantit.data.loader import DataLoader
    from quantit.data.macro import MacroLoader
    from quantit.features.cn_regime import compute_cn_etf_scores
    from quantit.markets.cn import CN_ETF_FALLBACK, all_cn_etf_symbols
    from quantit.policy.calendar import PolicyCalendar

    symbols = list(dict.fromkeys([*all_cn_etf_symbols(), CN_ETF_FALLBACK]))
    loader = DataLoader(provider=CompositeCNProvider())
    ohlcv = loader.load_multi(symbols, start, end, skip_missing=True)
    calendar = None
    for df in ohlcv.values():
        calendar = df.index if calendar is None else calendar.union(df.index)
    macros = MacroLoader().load(start, end, calendar=calendar, skip_missing=True)
    scores = compute_cn_etf_scores(ohlcv, macros, calendar=PolicyCalendar.load_cn())
    return ohlcv, scores


def run_research(
    strategy_id: str,
    symbols: list[str] | None = None,
    start: str = "2018-01-01",
    end: str = "2024-12-31",
    train: int = 504,
    test: int = 126,
    step: int = 126,
    promote: bool = False,
    report_path: str | Path | None = None,
) -> StudyResult:
    spec = get_spec(strategy_id)
    names = symbols or list(US_WATCHLIST)
    extra: dict[str, Any] | None = None
    if spec.kind == "multi":
        if strategy_id == "cn_etf_rotation":
            ohlcv, scores = _load_cn(start, end)
            label = "CN-ETF-ROTATION"
        else:
            ohlcv, scores = _load_hk(start, end)
            label = "HSTECH-ROTATION"
        if not ohlcv:
            raise SystemExit("No price data loaded")
        study = walk_forward(
            strategy_id,
            ohlcv,
            symbol=label,
            train=train,
            test=test,
            step=step,
            extra={"scores": scores},
        )
    else:
        frames = _load_us(names, start, end)
        if not frames:
            raise SystemExit("No price data loaded")
        studies = [
            walk_forward(
                strategy_id,
                df,
                symbol=sym,
                train=train,
                test=test,
                step=step,
                extra=extra,
            )
            for sym, df in frames.items()
        ]
        study = _combine(studies)

    dest = Path(report_path) if report_path else research_dir() / f"{strategy_id}_study.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    render_study(study, dest)
    print(f"Report: {dest}")
    print(f"OOS Sharpe {study.oos_sharpe:.2f} vs buy-and-hold {study.bh_sharpe:.2f}")
    print(f"Gate: {'PASS' if study.passed else 'FAIL'}")
    if study.gate and study.gate.reasons:
        for reason in study.gate.reasons:
            print(f"  - {reason}")
    if promote:
        written = maybe_promote(strategy_id, study.best_params, study.gate) if study.gate else None
        if written is None:
            print("Not promoted (gate failed or strategy is baseline-only).")
        else:
            print(f"Promoted parameters: {written}")
    return study
