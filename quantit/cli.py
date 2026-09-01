"""Command-line interface for QuantiT."""

from __future__ import annotations

import argparse


def _cmd_backtest(args: argparse.Namespace) -> None:
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


def _format_article(article) -> str:
    ts = article.datetime.strftime("%Y-%m-%d %H:%M")
    headline = article.headline or "(no headline)"
    source = article.source or "unknown"
    url = f"\n    {article.url}" if article.url else ""
    return f"[{ts}] {article.symbol} | {source}\n    {headline}{url}"


def _cmd_news(args: argparse.Namespace) -> None:
    from quantit.data.news import NewsAPIError, NewsClient

    try:
        client = NewsClient()
    except NewsAPIError as exc:
        raise SystemExit(str(exc)) from exc

    symbol = None if args.general else args.symbol

    if args.watch:
        print(f"Watching news every {args.interval}s (Ctrl+C to stop)...")

        def _print(article) -> None:
            print(_format_article(article), flush=True)

        try:
            client.watch(
                symbol=symbol,
                interval_sec=args.interval,
                lookback_days=args.lookback,
                callback=_print,
            )
        except NewsAPIError as exc:
            raise SystemExit(str(exc)) from exc
        except KeyboardInterrupt:
            print("\nStopped.")
        return

    try:
        articles = client.poll(symbol, lookback_days=args.lookback)
    except NewsAPIError as exc:
        raise SystemExit(str(exc)) from exc

    if not articles:
        print("No headlines returned.")
        return
    for article in articles[: args.limit]:
        print(_format_article(article))
        print()


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

    news = sub.add_parser("news", help="Fetch US equity news via Finnhub (testing, no trading)")
    news.add_argument("--symbol", default="AAPL")
    news.add_argument("--general", action="store_true", help="General market news instead of one symbol")
    news.add_argument("--lookback", type=int, default=1, help="Lookback days for company news")
    news.add_argument("--limit", type=int, default=20, help="Max headlines to print")
    news.add_argument("--watch", action="store_true", help="Poll repeatedly")
    news.add_argument("--interval", type=int, default=30, help="Watch interval in seconds")

    args = parser.parse_args()

    if args.command == "backtest":
        _cmd_backtest(args)
    elif args.command == "news":
        _cmd_news(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
