"""US equity news via Finnhub REST (polling, no live trading)."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from quantit.utils.config import get_config

FINNHUB_REGISTER_URL = "https://finnhub.io/register"


class NewsAPIError(RuntimeError):
    """Raised when the news API cannot be used."""


@dataclass
class NewsArticle:
    """Normalized news headline."""

    symbol: str
    headline: str
    summary: str
    source: str
    url: str
    datetime: datetime


class NewsProvider(ABC):
    """Abstract news source."""

    @abstractmethod
    def company_news(
        self,
        symbol: str,
        start: str | date | datetime,
        end: str | date | datetime,
    ) -> list[NewsArticle]:
        """Company-specific headlines."""

    @abstractmethod
    def market_news(self, category: str = "general") -> list[NewsArticle]:
        """General market headlines."""


def _as_day(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _parse_datetime(raw: int | float | str | None) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc)
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


class FinnhubNewsProvider(NewsProvider):
    """Finnhub company-news and market-news REST client."""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str | None = None, opener: Callable[..., object] | None = None) -> None:
        self.api_key = api_key if api_key is not None else get_config().finnhub_api_key
        self._opener = opener or urlopen
        if not self.api_key:
            raise NewsAPIError(
                "FINNHUB_API_KEY is not set. Register a free key at "
                f"{FINNHUB_REGISTER_URL} and export FINNHUB_API_KEY."
            )

    def _get(self, path: str, params: dict[str, str]) -> object:
        query = urlencode({**params, "token": self.api_key})
        url = f"{self.BASE_URL}{path}?{query}"
        request = Request(url, headers={"User-Agent": "QuantiT/0.1"})
        try:
            with self._opener(request, timeout=30) as resp:
                payload = resp.read()
        except HTTPError as exc:
            raise NewsAPIError(f"Finnhub HTTP {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise NewsAPIError(f"Finnhub request failed: {exc.reason}") from exc
        return json.loads(payload.decode("utf-8"))

    def _to_article(self, item: dict, symbol: str) -> NewsArticle:
        return NewsArticle(
            symbol=item.get("related") or symbol,
            headline=item.get("headline") or "",
            summary=item.get("summary") or "",
            source=item.get("source") or "",
            url=item.get("url") or "",
            datetime=_parse_datetime(item.get("datetime")),
        )

    def company_news(
        self,
        symbol: str,
        start: str | date | datetime,
        end: str | date | datetime,
    ) -> list[NewsArticle]:
        data = self._get(
            "/company-news",
            {"symbol": symbol, "from": _as_day(start), "to": _as_day(end)},
        )
        if not isinstance(data, list):
            raise NewsAPIError(f"Unexpected Finnhub company-news payload for {symbol}")
        return [self._to_article(item, symbol) for item in data if isinstance(item, dict)]

    def market_news(self, category: str = "general") -> list[NewsArticle]:
        data = self._get("/news", {"category": category})
        if not isinstance(data, list):
            raise NewsAPIError("Unexpected Finnhub market-news payload")
        return [self._to_article(item, category) for item in data if isinstance(item, dict)]


class NewsClient:
    """Poll and optionally watch news from a provider."""

    def __init__(self, provider: NewsProvider | None = None) -> None:
        self.provider = provider if provider is not None else FinnhubNewsProvider()

    def poll(
        self,
        symbol: str | None = None,
        lookback_days: int = 1,
        category: str = "general",
    ) -> list[NewsArticle]:
        """Fetch recent headlines. ``symbol=None`` uses general market news."""
        if symbol:
            end = date.today()
            start = end - timedelta(days=lookback_days)
            return self.provider.company_news(symbol, start, end)
        return self.provider.market_news(category=category)

    def watch(
        self,
        symbol: str | None = None,
        interval_sec: int = 30,
        lookback_days: int = 1,
        callback: Callable[[NewsArticle], None] | None = None,
        max_iterations: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Poll in a loop and invoke ``callback`` for newly seen headlines.

        Stops on KeyboardInterrupt, or after ``max_iterations`` (for tests).
        """
        seen: set[tuple[str, str]] = set()
        iteration = 0
        while True:
            articles = self.poll(symbol, lookback_days=lookback_days)
            for article in articles:
                key = (article.url, article.headline)
                if key in seen:
                    continue
                seen.add(key)
                if callback is not None:
                    callback(article)
            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                break
            try:
                sleep(interval_sec)
            except KeyboardInterrupt:
                break
