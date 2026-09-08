"""US EOD daily aggregates via Polygon/Massive, with history-window and rate guards.

Polygon.io rebranded to Massive (api.polygon.io and api.massive.com both work).
The free Stocks Basic plan includes adjusted daily bars for ~2 years at 5 calls
per minute — enough for the paper desk (400-day windows) but not for 2012-era
walk-forward studies. Older windows raise ValueError so FailoverProvider can
hand off to Yahoo. Tick/trade/quote/websocket endpoints are paid; this provider
only calls ``/v2/aggs``.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable

import pandas as pd

from quantit.data.provider import DataProvider
from quantit.utils.config import get_config

_POLYGON_AGGS = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
_FREE_DAILY_HISTORY_DAYS = 365 * 2
_SESSION_TZ = "America/New_York"
_PAD_DAYS = 7
# Free tier = 5 REST calls / minute. Stay just under that.
_MIN_INTERVAL_SEC = 12.5

_lock = threading.Lock()
_last_call_at = 0.0


class PolygonDailyProvider(DataProvider):
    """Daily OHLCV for US symbols from Polygon aggregates (adjusted)."""

    def __init__(
        self,
        api_key: str | None = None,
        max_history_days: int = _FREE_DAILY_HISTORY_DAYS,
        min_interval_sec: float = _MIN_INTERVAL_SEC,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.max_history_days = max_history_days
        self.min_interval_sec = min_interval_sec
        self._opener = opener or urllib.request.urlopen

    def _token(self) -> str:
        key = get_config().polygon_api_key if self.api_key is None else self.api_key
        if not key:
            raise ValueError("PolygonDailyProvider needs POLYGON_API_KEY")
        return key

    def _throttle(self) -> None:
        global _last_call_at
        if self.min_interval_sec <= 0:
            return
        with _lock:
            now = time.monotonic()
            wait = self.min_interval_sec - (now - _last_call_at)
            if wait > 0:
                time.sleep(wait)
            _last_call_at = time.monotonic()

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if interval != "1d":
            raise ValueError(f"PolygonDailyProvider only supports 1d, got {interval!r}")
        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
        if end_ts <= start_ts:
            raise ValueError(f"Empty range for {symbol}: {start_ts} -> {end_ts}")

        now = pd.Timestamp.now(tz="UTC").replace(tzinfo=None).normalize()
        oldest = now - pd.Timedelta(days=self.max_history_days)
        if start_ts < oldest - pd.Timedelta(days=_PAD_DAYS):
            raise ValueError(
                f"{symbol}: start {start_ts.date()} older than Polygon free window "
                f"(~{self.max_history_days} days); use a longer-history provider"
            )

        ticker = symbol.strip().upper()
        params = urllib.parse.urlencode(
            {
                "adjusted": "true",
                "sort": "asc",
                "limit": 50000,
                "apiKey": self._token(),
            }
        )
        url = (
            _POLYGON_AGGS.format(
                ticker=urllib.parse.quote(ticker, safe=""),
                start=start_ts.strftime("%Y-%m-%d"),
                end=end_ts.strftime("%Y-%m-%d"),
            )
            + "?"
            + params
        )
        self._throttle()
        req = urllib.request.Request(url, headers={"User-Agent": "QuantiT/0.1"})
        try:
            with self._opener(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ValueError(
                f"No data returned for {symbol} via Polygon: HTTP {exc.code} {exc.reason}"
            ) from exc
        except Exception as exc:
            raise ValueError(f"No data returned for {symbol} via Polygon: {exc}") from exc

        status = str(payload.get("status") or "")
        if status.upper() in {"NOT_AUTHORIZED", "ERROR"}:
            raise ValueError(
                f"No data returned for {symbol} via Polygon: {payload.get('message') or status}"
            )
        rows = payload.get("results") or []
        if not rows:
            raise ValueError(f"No data returned for {symbol} via Polygon: empty aggregates")

        times = [row["t"] for row in rows]
        et = pd.to_datetime(times, unit="ms", utc=True).tz_convert(_SESSION_TZ)
        df = pd.DataFrame(
            {
                "open": [row.get("o") for row in rows],
                "high": [row.get("h") for row in rows],
                "low": [row.get("l") for row in rows],
                "close": [row.get("c") for row in rows],
                "volume": [row.get("v") for row in rows],
            },
            index=pd.DatetimeIndex(et.normalize().tz_localize(None)),
        )
        df.index.name = "date"
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df[(df.index >= start_ts) & (df.index < end_ts)]
        df = df.dropna(subset=["close"])
        if df.empty:
            raise ValueError(f"No data returned for {symbol} via Polygon ({start_ts} to {end_ts})")
        return df
