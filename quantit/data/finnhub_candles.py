"""US EOD daily candles via Finnhub (keyed REST), with history-window guard.

The free Finnhub tier covers US equities/ETFs with daily candles for ~5 years —
plenty for the paper desk (400-day runner windows, 45-day overview marks) but not
for 2012-era walk-forward studies. Requests older than the window raise ValueError
so a FailoverProvider chain can hand those off to Yahoo automatically.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import pandas as pd

from quantit.data.provider import DataProvider
from quantit.utils.config import get_config

_FINNHUB_CANDLE = "https://finnhub.io/api/v1/stock/candle"
_FREE_DAILY_HISTORY_DAYS = 365 * 5
_SESSION_TZ = "America/New_York"
_PAD_DAYS = 7


class FinnhubDailyProvider(DataProvider):
    """Daily OHLCV for US symbols from ``/stock/candle?resolution=D``."""

    def __init__(
        self,
        api_key: str | None = None,
        max_history_days: int = _FREE_DAILY_HISTORY_DAYS,
    ) -> None:
        self.api_key = api_key
        self.max_history_days = max_history_days

    def _token(self) -> str:
        key = self.api_key or get_config().finnhub_api_key
        if not key:
            raise ValueError("FinnhubDailyProvider needs FINNHUB_API_KEY")
        return key

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if interval != "1d":
            raise ValueError(f"FinnhubDailyProvider only supports 1d, got {interval!r}")
        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
        if end_ts <= start_ts:
            raise ValueError(f"Empty range for {symbol}: {start_ts} -> {end_ts}")

        oldest = pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=self.max_history_days)
        if start_ts < oldest - pd.Timedelta(days=_PAD_DAYS):
            raise ValueError(
                f"{symbol}: start {start_ts.date()} older than Finnhub free window "
                f"(~{self.max_history_days} days); use a longer-history provider"
            )

        params = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "resolution": "D",
                "from": int(start_ts.tz_localize("UTC").timestamp()),
                "to": int(end_ts.tz_localize("UTC").timestamp() + 86400),
                "token": self._token(),
            }
        )
        req = urllib.request.Request(f"{_FINNHUB_CANDLE}?{params}", headers={"User-Agent": "QuantiT/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ValueError(
                f"No data returned for {symbol} via Finnhub: HTTP {exc.code} {exc.reason}"
            ) from exc
        except Exception as exc:
            raise ValueError(f"No data returned for {symbol} via Finnhub: {exc}") from exc

        if payload.get("s") != "ok":
            raise ValueError(f"No data returned for {symbol} via Finnhub: {payload.get('s')}")

        times = payload.get("t") or []
        closes = payload.get("c") or []
        if not times or not closes:
            raise ValueError(f"No data returned for {symbol} via Finnhub: empty candles")
        et = pd.to_datetime(times, unit="s", utc=True).tz_convert(_SESSION_TZ)
        df = pd.DataFrame(
            {
                "open": payload.get("o"),
                "high": payload.get("h"),
                "low": payload.get("l"),
                "close": closes,
                "volume": payload.get("v"),
            },
            index=pd.DatetimeIndex(et.normalize().tz_localize(None)),
        )
        df.index.name = "date"
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df[(df.index >= start_ts) & (df.index < end_ts)]
        df = df.dropna(subset=["close"])
        if df.empty:
            raise ValueError(f"No data returned for {symbol} via Finnhub ({start_ts} to {end_ts})")
        return df
