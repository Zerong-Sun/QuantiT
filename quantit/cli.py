"""Command-line interface for QuantiT."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantiT quantitative trading platform")
    parser.add_argument("--version", action="version", version="QuantiT 0.1.0")
    sub = parser.add_subparsers(dest="command")

    backtest = sub.add_parser("backtest", help="Run a backtest")
    backtest.add_argument("--symbol", default="AAPL")
    backtest.add_argument("--start", default="2020-01-01")
    backtest.add_argument("--end", default="2024-12-31")
    backtest.add_argument("--fast", type=int, default=10)
    backtest.add_argument("--slow", type=int, default=30)

    args = parser.parse_args()

    if args.command == "backtest":
        from quantit.analysis.metrics import compute_metrics, format_metrics
        from quantit.data.loader import DataLoader
        from quantit.engine.backtester import Backtester
        from quantit.strategy.technical import MACrossoverStrategy

        loader = DataLoader()
        data = loader.load(args.symbol, args.start, args.end)
        strategy = MACrossoverStrategy(fast_period=args.fast, slow_period=args.slow)
        result = Backtester().run(strategy, data, symbol=args.symbol)
        metrics = compute_metrics(result)
        print(format_metrics(metrics))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
