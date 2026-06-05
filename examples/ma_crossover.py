#!/usr/bin/env python3
"""MA crossover backtest example."""

from quantit.analysis.metrics import compute_metrics, format_metrics
from quantit.data.loader import DataLoader
from quantit.engine.backtester import Backtester
from quantit.strategy.technical import MACrossoverStrategy


def main() -> None:
    symbol = "AAPL"
    start = "2020-01-01"
    end = "2024-12-31"

    print(f"Loading {symbol} data ({start} to {end})...")
    loader = DataLoader()
    data = loader.load(symbol, start, end)

    print(f"Loaded {len(data)} bars")
    print(f"Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")

    strategy = MACrossoverStrategy(fast_period=10, slow_period=30)
    backtester = Backtester(initial_cash=100_000)
    result = backtester.run(strategy, data, symbol=symbol)

    metrics = compute_metrics(result)
    print("\n=== Backtest Results ===")
    print(format_metrics(metrics))
    print(f"\nTrades executed: {len(result.trades)}")


if __name__ == "__main__":
    main()
