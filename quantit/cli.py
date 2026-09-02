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


def _cmd_research(args: argparse.Namespace) -> None:
    from quantit.paper.capital import US_WATCHLIST
    from quantit.research.run import run_research

    symbols = [s.strip() for s in (args.symbols or ",".join(US_WATCHLIST)).split(",") if s.strip()]
    run_research(
        args.strategy,
        symbols=symbols,
        start=args.start,
        end=args.end,
        train=args.train,
        test=args.test,
        step=args.step,
        promote=args.promote,
        report_path=args.report or None,
    )


def _cmd_brief(args: argparse.Namespace) -> None:
    from quantit.research.brief import (
        BriefError,
        build_brief_markdown,
        call_llm,
        parse_llm_proposal,
        write_brief,
        write_proposal,
    )

    markdown, _articles = build_brief_markdown(lookback_days=args.lookback)
    path = write_brief(markdown)
    print(f"Brief written to {path}")
    print("Open it in Cursor and ask for a policy-calendar patch. Not a trade signal.")
    if not args.llm:
        return
    try:
        raw = call_llm(markdown)
        payload = parse_llm_proposal(raw)
    except BriefError as exc:
        raise SystemExit(str(exc)) from exc
    dest = write_proposal(payload)
    print(f"LLM proposal written to {dest} (not merged, runner does not read this file).")


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


def _cmd_serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install the paper extra: pip install -e '.[paper]'") from exc

    import threading
    import time
    import webbrowser

    from quantit.api.app import create_app

    url = f"http://{args.host}:{args.port}/"
    print(f"Paper terminal UI: {url}", flush=True)
    print("Do not open web/index.html as a file.", flush=True)

    if args.open_browser:
        def _open() -> None:
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        create_app,
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


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

    serve = sub.add_parser("serve", help="Run the paper trading API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        default=True,
        help="Open the UI in a browser (default)",
    )
    serve.add_argument(
        "--no-open",
        dest="open_browser",
        action="store_false",
        help="Do not open a browser",
    )

    research = sub.add_parser("research", help="Walk-forward parameter study (OOS vs buy-and-hold)")
    research.add_argument("--strategy", default="tsmom", help="tsmom, us_book, ma_crossover, rsi_mean_reversion, theme_rotation")
    research.add_argument("--symbols", default="", help="Comma-separated US symbols (default: paper watchlist)")
    research.add_argument("--start", default="2018-01-01")
    research.add_argument("--end", default="2024-12-31")
    research.add_argument("--train", type=int, default=504)
    research.add_argument("--test", type=int, default=126)
    research.add_argument("--step", type=int, default=126)
    research.add_argument("--promote", action="store_true", help="Write active_params.yaml if tsmom passes the gate")
    research.add_argument("--report", default="", help="HTML report path")

    brief = sub.add_parser("brief", help="Policy/international brief from Finnhub (no sentiment trading)")
    brief.add_argument("--lookback", type=int, default=7)
    brief.add_argument("--llm", action="store_true", help="Optional LLM JSON proposal (not auto-merged)")

    args = parser.parse_args()

    if args.command == "backtest":
        _cmd_backtest(args)
    elif args.command == "news":
        _cmd_news(args)
    elif args.command == "serve":
        _cmd_serve(args)
    elif args.command == "research":
        _cmd_research(args)
    elif args.command == "brief":
        _cmd_brief(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
