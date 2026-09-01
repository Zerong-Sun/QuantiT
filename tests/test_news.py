"""Finnhub news client tests (mocked HTTP, no API key required)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request

import pytest

from quantit.data.news import FinnhubNewsProvider, NewsAPIError, NewsArticle, NewsClient


class FakeResponse:
    def __init__(self, payload: object) -> None:
        body = json.dumps(payload) if not isinstance(payload, (bytes, str)) else payload
        self._body = body.encode("utf-8") if isinstance(body, str) else body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_missing_api_key() -> None:
    with pytest.raises(NewsAPIError, match="FINNHUB_API_KEY"):
        FinnhubNewsProvider(api_key="")


def test_parses_company_news() -> None:
    payload = [
        {
            "headline": "Apple beats earnings",
            "summary": "Revenue up",
            "source": "Reuters",
            "url": "https://example.com/aapl",
            "datetime": 1_700_000_000,
            "related": "AAPL",
        }
    ]
    calls: list[str] = []

    def opener(request: Request, timeout: int = 30) -> FakeResponse:
        calls.append(request.full_url)
        return FakeResponse(payload)

    provider = FinnhubNewsProvider(api_key="test-key", opener=opener)
    articles = provider.company_news("AAPL", "2024-01-01", "2024-01-02")

    assert len(articles) == 1
    article = articles[0]
    assert article.headline == "Apple beats earnings"
    assert article.source == "Reuters"
    assert article.url == "https://example.com/aapl"
    assert article.symbol == "AAPL"
    assert article.datetime == datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)
    assert "token=test-key" in calls[0]
    assert "symbol=AAPL" in calls[0]


def test_poll_and_watch_dedupes() -> None:
    articles = [
        NewsArticle(
            symbol="AAPL",
            headline="One",
            summary="",
            source="X",
            url="https://example.com/1",
            datetime=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
        NewsArticle(
            symbol="AAPL",
            headline="Two",
            summary="",
            source="X",
            url="https://example.com/2",
            datetime=datetime(2024, 1, 2, tzinfo=timezone.utc),
        ),
    ]

    class StubProvider:
        def company_news(self, symbol, start, end):
            return articles

        def market_news(self, category="general"):
            return []

    seen: list[str] = []
    sleeps: list[float] = []
    client = NewsClient(provider=StubProvider())
    client.watch(
        symbol="AAPL",
        interval_sec=5,
        callback=lambda a: seen.append(a.headline),
        max_iterations=2,
        sleep=sleeps.append,
    )

    assert seen == ["One", "Two"]
    assert sleeps == [5]
