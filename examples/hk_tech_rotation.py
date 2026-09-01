#!/usr/bin/env python3
"""Hang Seng TECH / Chinese internet monthly theme rotation (HK, long horizon)."""

from __future__ import annotations

from pathlib import Path

from quantit.analysis.metrics import compute_metrics, format_metrics
from quantit.analysis.report import generate_report
from quantit.data.loader import DataLoader
from quantit.data.macro import MacroLoader
from quantit.engine.backtester import Backtester
from quantit.features.regime import compute_theme_scores
from quantit.markets.hk import HK_PROFILE, HSTECH_THEMES, all_hstech_symbols
from quantit.policy.calendar import PolicyCalendar
from quantit.strategy.regime import ThemeRotationStrategy


def main() -> None:
    start = "2020-01-01"
    end = "2026-08-31"
    symbols = all_hstech_symbols()

    print(f"Loading {len(symbols)} HK names ({start} to {end})...")
    loader = DataLoader()
    ohlcv = loader.load_multi(symbols, start, end, skip_missing=True)
    missing = [s for s in symbols if s not in ohlcv]
    if missing:
        print(f"Skipped (no data): {', '.join(missing)}")
    if not ohlcv:
        print("No HK equity data loaded; aborting.")
        return

    calendar_index = None
    for df in ohlcv.values():
        calendar_index = df.index if calendar_index is None else calendar_index.union(df.index)
    calendar_index = calendar_index.sort_values()

    print("Loading macro series (aligned to HK sessions)...")
    macros = MacroLoader(loader).load(start, end, calendar=calendar_index, skip_missing=True)
    skipped = macros.attrs.get("skipped") or []
    if skipped:
        print(f"Skipped macros: {', '.join(skipped)}")

    print("Scoring themes (demand + policy calendar + international)...")
    scores = compute_theme_scores(ohlcv, macros, calendar=PolicyCalendar.load_default())
    print(f"Score window: {scores.index[0].date()} → {scores.index[-1].date()}")
    print(f"Latest scores:\n{scores.iloc[-1].to_string()}")

    strategy = ThemeRotationStrategy(scores=scores, themes=HSTECH_THEMES)
    backtester = Backtester(
        initial_cash=1_000_000.0,
        commission_rate=HK_PROFILE.all_in_commission_rate,
        slippage_rate=HK_PROFILE.slippage_rate,
    )
    print("\nRunning monthly multi-asset backtest...")
    result = backtester.run(strategy, ohlcv, symbol="HSTECH-ROTATION")
    metrics = compute_metrics(result)
    print("\n=== HK Tech Theme Rotation ===")
    print(format_metrics(metrics))
    print(f"Trades executed: {len(result.trades)}")

    report_path = Path(__file__).resolve().parent / "hk_tech_rotation_report.html"
    generate_report(result, report_path)
    print(f"\nHTML report saved to {report_path}")


if __name__ == "__main__":
    main()
