"""HKEX 5-digit warrant / CBBC bars. Yahoo often has no history for these codes."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime

import pandas as pd

from quantit.data.provider import DataProvider, YahooFinanceProvider
from quantit.markets.assets import asset_class

_EM_KLINE = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    "?secid=116.{code}&fields1=f1,f2,f3,f4,f5,f6"
    "&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
    "&klt=101&fqt=1&lmt=800&end=20500000"
)


def parse_eastmoney_klines(klines: list[str]) -> pd.DataFrame:
    """Parse Eastmoney daily kline strings: date,open,close,high,low,volume,..."""
    rows: list[dict] = []
    for raw in klines:
        parts = str(raw).split(",")
        if len(parts) < 6:
            continue
        rows.append(
            {
                "date": pd.Timestamp(parts[0]),
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows).set_index("date").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


class EastmoneyHKStructuredProvider(DataProvider):
    """Daily OHLCV for HKEX derivative warrants and CBBCs via Eastmoney."""

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if interval != "1d":
            raise ValueError(f"HK structured products only support 1d bars, got {interval!r}")
        code = symbol.split(".")[0].lstrip("0") or "0"
        url = _EM_KLINE.format(code=code)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 QuantiT"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"No data returned for {symbol} ({start} to {end})") from exc
        data = payload.get("data") or {}
        klines = data.get("klines") or []
        df = parse_eastmoney_klines(klines)
        if df.empty:
            raise ValueError(f"No data returned for {symbol} ({start} to {end})")
        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize() + pd.Timedelta(days=1)
        df = df[(df.index >= start_ts) & (df.index < end_ts)]
        if df.empty:
            raise ValueError(f"No data returned for {symbol} ({start} to {end})")
        return df


class HKMarketProvider(DataProvider):
    """Yahoo for equities/ETFs; Eastmoney for 5-digit warrants/CBBCs."""

    def __init__(
        self,
        equity: DataProvider | None = None,
        structured: DataProvider | None = None,
    ) -> None:
        self.equity = equity or YahooFinanceProvider()
        self.structured = structured or EastmoneyHKStructuredProvider()

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if asset_class("hk", symbol) == "warrant":
            return self.structured.fetch(symbol, start, end, interval)
        return self.equity.fetch(symbol, start, end, interval)
