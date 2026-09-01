#!/usr/bin/env python3
"""Print recent US equity headlines via Finnhub (testing only, no trading)."""

from quantit.data.news import NewsAPIError, NewsClient


def main() -> None:
    try:
        client = NewsClient()
    except NewsAPIError as exc:
        raise SystemExit(str(exc)) from exc

    symbol = "AAPL"
    print(f"Fetching recent {symbol} headlines...")
    articles = client.poll(symbol, lookback_days=3)
    if not articles:
        print("No headlines returned.")
        return
    for article in articles[:15]:
        ts = article.datetime.strftime("%Y-%m-%d %H:%M")
        print(f"[{ts}] {article.source}: {article.headline}")
        if article.url:
            print(f"    {article.url}")


if __name__ == "__main__":
    main()
