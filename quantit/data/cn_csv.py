"""Local A-share ETF history (materials CSV) plus AkShare fallback."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from quantit.data.provider import DataProvider


def default_cn_etf_csv() -> Path | None:
    """``QUANTIT_CN_ETF_CSV`` if it exists, else ``materials/etf_history_clean.csv``."""
    env = os.environ.get("QUANTIT_CN_ETF_CSV", "").strip()
    if env:
        path = Path(env)
        if path.is_file():
            return path
    repo = Path(__file__).resolve().parents[2]
    candidate = repo / "materials" / "etf_history_clean.csv"
    return candidate if candidate.is_file() else None


class CsvETFProvider(DataProvider):
    """Daily OHLCV from ``code,name,date,open,close,high,low,vol_hand,amt_yuan``."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            self.path = default_cn_etf_csv()
        else:
            self.path = Path(path)
        self._by_code: dict[str, pd.DataFrame] | None = None

    def _frames(self) -> dict[str, pd.DataFrame]:
        if self._by_code is not None:
            return self._by_code
        if self.path is None or not self.path.is_file():
            self._by_code = {}
            return self._by_code
        raw = pd.read_csv(self.path, dtype={"code": str})
        required = {"code", "date", "open", "high", "low", "close"}
        missing = required - set(raw.columns)
        if missing:
            raise ValueError(f"ETF CSV missing columns: {sorted(missing)}")
        raw = raw.copy()
        raw["code"] = raw["code"].astype(str).str.split(".").str[0].str.zfill(6)
        raw["date"] = pd.to_datetime(raw["date"])
        if "vol_hand" in raw.columns:
            raw["volume"] = raw["vol_hand"].astype(float) * 100.0
        elif "volume" not in raw.columns:
            raw["volume"] = 0.0
        frames: dict[str, pd.DataFrame] = {}
        for code, group in raw.groupby("code", sort=False):
            out = group.set_index("date")[["open", "high", "low", "close", "volume"]].astype(float)
            idx = pd.DatetimeIndex(pd.to_datetime(out.index))
            if idx.tz is not None:
                idx = idx.tz_convert(None)
            out.index = idx
            out.index.name = "date"
            frames[str(code)] = out.sort_index()
            frames[str(code)] = frames[str(code)][~frames[str(code)].index.duplicated(keep="last")]
        self._by_code = frames
        return self._by_code

    @staticmethod
    def _code(symbol: str) -> str:
        return symbol.strip().upper().split(".")[0].zfill(6)

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if interval != "1d":
            raise ValueError(f"Unsupported A-share CSV interval: {interval}")
        frames = self._frames()
        code = self._code(symbol)
        df = frames.get(code)
        if df is None or df.empty:
            raise ValueError(f"No data returned for {symbol} ({start} to {end})")
        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
        sliced = df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()
        if sliced.empty:
            raise ValueError(f"No data returned for {symbol} ({start} to {end})")
        return sliced


class CompositeCNProvider(DataProvider):
    """Daily bars: CSV first, AkShare fills gaps; minutes are live-only."""

    def __init__(
        self,
        csv: CsvETFProvider | None = None,
        live: DataProvider | None = None,
    ) -> None:
        self.csv = csv if csv is not None else CsvETFProvider()
        self._live = live

    @staticmethod
    def _covers(csv_df: pd.DataFrame | None, start: pd.Timestamp, end: pd.Timestamp) -> bool:
        """True if CSV spans the request, allowing weekend/holiday session gaps."""
        if csv_df is None or csv_df.empty:
            return False
        pad = pd.Timedelta(days=5)
        return csv_df.index.min() <= start + pad and csv_df.index.max() >= end - pad

    @property
    def live(self) -> DataProvider:
        if self._live is None:
            from quantit.markets.cn import AkShareCNProvider

            self._live = AkShareCNProvider()
        return self._live

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if interval != "1d":
            return self.live.fetch(symbol, start, end, interval)

        csv_df: pd.DataFrame | None = None
        try:
            csv_df = self.csv.fetch(symbol, start, end, interval)
        except ValueError:
            csv_df = None

        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
        if self._covers(csv_df, start_ts, end_ts):
            return csv_df

        try:
            live_df = self.live.fetch(symbol, start, end, interval)
        except ValueError:
            if csv_df is not None and not csv_df.empty:
                return csv_df
            raise

        if csv_df is None or csv_df.empty:
            return live_df
        combined = pd.concat([live_df, csv_df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        combined.index.name = "date"
        return combined
