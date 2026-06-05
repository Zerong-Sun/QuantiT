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
        df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)

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
