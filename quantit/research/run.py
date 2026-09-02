"""CLI entry for walk-forward research."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from quantit.research.params import research_dir
from quantit.research.promote import maybe_promote
from quantit.research.report import regime_summary, render_study, write_folds_csv
from quantit.research.specs import get_spec
from quantit.research.universes import (
    US_QUALITY,
    US_QUALITY_BENCHMARK,
    YAHOO_ALIASES,
    default_research_symbols,
)
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
        bh_drawdown=min(s.bh_drawdown for s in studies),
        best_params=best_params,
    )
    from quantit.research.gates import evaluate_gates

    combined.gate = evaluate_gates(
        oos_sharpe=combined.oos_sharpe,
        oos_drawdown=combined.oos_drawdown,
        oos_trades=combined.oos_trades,
        buy_hold_sharpe=combined.bh_sharpe,
        buy_hold_drawdown=combined.bh_drawdown,
    )
    return combined


def _is_cn_symbol(symbol: str) -> bool:
    upper = symbol.strip().upper()
    return upper.endswith(".SS") or upper.endswith(".SZ") or upper.endswith(".SH")


def _load_frames(symbols: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    from quantit.data.cn_csv import CompositeCNProvider
    from quantit.data.loader import DataLoader

    us_hk = [s for s in symbols if not _is_cn_symbol(s)]
    cn = [s for s in symbols if _is_cn_symbol(s)]
    frames: dict[str, pd.DataFrame] = {}
    if us_hk:
        loader = DataLoader()
        for sym in us_hk:
            fetch = YAHOO_ALIASES.get(sym, sym)
            try:
                df = loader.load(fetch, start, end)
            except Exception:
                continue
            if df is not None and not df.empty:
                frames[sym] = df
    if cn:
        frames.update(
            DataLoader(provider=CompositeCNProvider()).load_multi(cn, start, end, skip_missing=True)
        )
    return frames


def _print_coverage(frames: dict[str, pd.DataFrame], requested_start: str) -> None:
    if not frames:
        return
    first = min(df.index.min() for df in frames.values())
    last = max(df.index.max() for df in frames.values())
    print(
        f"Loaded {len(frames)} symbols {pd.Timestamp(first).date()} → {pd.Timestamp(last).date()} "
        f"(requested start {requested_start})"
    )
    missing_early = [
        sym
        for sym, df in frames.items()
        if pd.Timestamp(df.index.min()) > pd.Timestamp(requested_start) + pd.Timedelta(days=30)
    ]
    if missing_early:
        print("Later-start names: " + ", ".join(f"{s}@{frames[s].index.min().date()}" for s in missing_early))


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
    start: str = "2012-01-01",
    end: str = "2024-12-31",
    train: int = 504,
    test: int = 126,
    step: int = 126,
    promote: bool = False,
    report_path: str | Path | None = None,
) -> StudyResult:
    spec = get_spec(strategy_id)
    names = symbols or default_research_symbols()
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
        _print_coverage(ohlcv, start)
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
        frames = _load_frames(names, start, end)
        if not frames:
            raise SystemExit("No price data loaded")
        _print_coverage(frames, start)
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
        if len(frames) > 1:
            from quantit.research.search import buy_and_hold_metrics

            pool = buy_and_hold_metrics(frames, "POOL-EW")
            print(
                f"Pool equal-weight buy-and-hold Sharpe {float(pool.get('sharpe_ratio') or 0):.2f} | "
                f"DD {float(pool.get('max_drawdown') or 0):.2%} (full loaded window)"
            )

    dest = Path(report_path) if report_path else research_dir() / f"{strategy_id}_study.html"
    print(f"OOS Sharpe {study.oos_sharpe:.2f} vs buy-and-hold {study.bh_sharpe:.2f}")
    print(f"OOS max DD {study.oos_drawdown:.2%} vs buy-and-hold {study.bh_drawdown:.2%}")
    print(f"Gate: {'PASS' if study.passed else 'FAIL'}")
    if study.gate and study.gate.reasons:
        for reason in study.gate.reasons:
            print(f"  - {reason}")
    by_reg = regime_summary(study)
    print(
        f"Bull-fold OOS Sharpe {by_reg['bull']:.2f} (n={int(by_reg['bull_n'])}) | "
        f"Bear-fold OOS Sharpe {by_reg['bear']:.2f} (n={int(by_reg['bear_n'])})"
    )
    skip_counts: Counter[Any] = Counter()
    scale_counts: Counter[Any] = Counter()
    for fold in study.folds:
        if "skip" in fold.params:
            skip_counts[fold.params["skip"]] += 1
        if "risk_off_scale" in fold.params:
            scale_counts[fold.params["risk_off_scale"]] += 1
    if skip_counts:
        print(f"Fold skip votes: {dict(skip_counts)}")
    if scale_counts:
        print(f"Fold risk_off_scale votes: {dict(scale_counts)}")
    print(f"Last-fold params: {study.best_params}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    render_study(study, dest)
    csv_path = dest.with_suffix(".csv")
    write_folds_csv(study, csv_path)
    print(f"Report: {dest}")
    print(f"Folds CSV: {csv_path}")
    if spec.kind != "multi" and set(names) == set(US_QUALITY):
        try:
            brk = _load_frames([US_QUALITY_BENCHMARK], start, end)
            if brk:
                from quantit.research.search import buy_and_hold_metrics

                frame = next(iter(brk.values()))
                m = buy_and_hold_metrics(frame, US_QUALITY_BENCHMARK)
                print(
                    f"{US_QUALITY_BENCHMARK} buy-and-hold Sharpe "
                    f"{float(m.get('sharpe_ratio') or 0):.2f} (reference only)"
                )
        except (SystemExit, ValueError, KeyError):
            pass
    if promote:
        written = maybe_promote(strategy_id, study.best_params, study.gate) if study.gate else None
        if written is None:
            print("Not promoted (gate failed or strategy is baseline-only).")
        else:
            print(f"Promoted parameters: {written}")
    return study
