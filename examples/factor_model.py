#!/usr/bin/env python3
"""Factor model example — compute factors and run a factor-based backtest."""

from pathlib import Path

from quantit.analysis.metrics import compute_metrics, format_metrics
from quantit.analysis.report import generate_report
from quantit.data.loader import DataLoader
from quantit.engine.backtester import Backtester
from quantit.features.registry import default_registry
from quantit.strategy.technical import RSIMeanReversionStrategy


def main() -> None:
    symbol = "AAPL"
    start = "2020-01-01"
    end = "2024-12-31"

    print(f"Loading {symbol} data...")
    loader = DataLoader()
    data = loader.load(symbol, start, end)

    print("Computing factors...")
    registry = default_registry()
    enriched = registry.compute(data, names=["rsi_14", "macd", "bb", "atr_14"])
    print(f"Available factor columns: {[c for c in enriched.columns if c not in data.columns]}")

    print("\nRunning RSI mean-reversion backtest...")
    strategy = RSIMeanReversionStrategy(buy_threshold=30, sell_threshold=70)
    backtester = Backtester(initial_cash=100_000)
    result = backtester.run(strategy, data, symbol=symbol)

    metrics = compute_metrics(result)
    print("\n=== RSI Mean Reversion Results ===")
    print(format_metrics(metrics))

    report_path = Path(__file__).resolve().parent / "backtest_report.html"
    generate_report(result, report_path)
    print(f"\nHTML report saved to {report_path}")


if __name__ == "__main__":
    main()
