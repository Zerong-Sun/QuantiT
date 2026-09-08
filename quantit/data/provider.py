"""Data provider abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd


class DataProvider(ABC):
    """Abstract interface for market data providers."""

    @abstractmethod
    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch OHLCV data for a symbol."""


class YahooFinanceProvider(DataProvider):
    """Yahoo Finance data provider via yfinance."""

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        try:
            df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
        except Exception as exc:
            raise ValueError(f"No data returned for {symbol} ({start} to {end}): {exc}") from exc

        if df.empty:
            raise ValueError(f"No data returned for {symbol} ({start} to {end})")

        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        df.index.name = "date"
        df = df[["open", "high", "low", "close", "volume"]]
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df


class FailoverProvider(DataProvider):
    """Try ``primary`` first; on any failure, fall back to ``fallback``.

    Lets a market run off a cheap keyed/EOD source (Finnhub, Eastmoney) and keep
    Yahoo only as a safety net, instead of hammering Yahoo on every request.
    """

    def __init__(
        self,
        primary: DataProvider,
        fallback: DataProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback

    @property
    def providers(self) -> tuple[DataProvider, ...]:
        out: list[DataProvider] = []
        stack = [self.primary, self.fallback]
        while stack:
            provider = stack.pop()
            if provider in out:
                continue
            out.append(provider)
            for attr in ("primary", "fallback", "equity", "structured"):
                nested = getattr(provider, attr, None)
                if isinstance(nested, DataProvider) and nested is not provider:
                    stack.append(nested)
        return tuple(out)

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        primary_error: Exception | None = None
        try:
            return self.primary.fetch(symbol, start, end, interval)
        except Exception as exc:  # noqa: BLE001 - any primary failure hands over
            primary_error = exc
        try:
            return self.fallback.fetch(symbol, start, end, interval)
        except Exception as fallback_exc:  # noqa: BLE001
            detail = f"{type(primary_error).__name__}: {primary_error}" if primary_error else "n/a"
            raise ValueError(
                f"No data returned for {symbol} from primary "
                f"({type(self.primary).__name__} [{detail}]) or fallback "
                f"({type(self.fallback).__name__} [{type(fallback_exc).__name__}: {fallback_exc}])"
            ) from fallback_exc
