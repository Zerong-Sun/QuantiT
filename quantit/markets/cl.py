"""Closeloop CSI300 paper venue: quotes from the Qlib dump, never Yahoo or CN ETF CSV.

This adapter must not import ``closeloop`` (isolation). It only reads the dump directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from quantit.data.provider import DataProvider
from quantit.markets.adapter import MarketAdapter
from quantit.markets.base import MarketProfile
from quantit.markets.types import Quote

CL_PROFILE = MarketProfile(
    name="cl",
    currency="CNY",
    trading_days_per_year=242,
    commission_rate=0.0003,
    stamp_duty_rate=0.0005,
    slippage_rate=0.0005,
    lot_size_note="CSI300 names in lots of 100. Isolated from us/hk/cn paper books.",
)


def closeloop_dump_dir() -> Path:
    override = os.environ.get("CLOSELOOP_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".quantit" / "closeloop" / "qlib_cn"


def normalize_cl_symbol(raw: str) -> str:
    s = raw.strip().upper().replace(".SH", "").replace(".SS", "").replace(".SZ", "")
    if s.startswith("SH") or s.startswith("SZ"):
        return s
    digits = "".join(ch for ch in s if ch.isdigit())[-6:].zfill(6)
    if digits.startswith("6") or digits.startswith("9"):
        return f"SH{digits}"
    return f"SZ{digits}"


class CloseloopDumpProvider(DataProvider):
    """Read daily OHLCV for one instrument from panel.parquet."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else closeloop_dump_dir()

    def fetch(
        self,
        symbol: str,
        start: str | object,
        end: str | object,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if interval != "1d":
            raise ValueError("cl market only supports 1d bars from the Qlib dump")
        parquet = self.data_dir / "panel.parquet"
        if not parquet.is_file():
            raise ValueError("no closeloop dump (panel.parquet missing); ingest CSI300 first")
        panel = pd.read_parquet(parquet)
        panel.index = pd.DatetimeIndex(panel.index)
        inst = normalize_cl_symbol(str(symbol))
        fields = ("open", "high", "low", "close", "volume")
        try:
            frame = pd.DataFrame({f: panel[(f, inst)] for f in fields})
        except KeyError as exc:
            raise ValueError(f"No dump bars for {inst}") from exc
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        out = frame.loc[start_ts:end_ts].dropna(how="all")
        if out.empty:
            # Dumps are often historical CSI300; still serve the last dump bars as the quote.
            out = frame.dropna(how="all").iloc[-14:]
        if out.empty:
            raise ValueError(f"No dump bars for {inst} in range")
        return out


class CLAdapter(MarketAdapter):
    market_id = "cl"
    profile = CL_PROFILE
    timezone = "Asia/Shanghai"
    session_hours = "09:30-15:00 CST"
    t_plus = 1
    supported_intervals = ("1d",)

    def __init__(self, provider: DataProvider | None = None, data_dir: Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir is not None else closeloop_dump_dir()
        super().__init__(provider if provider is not None else CloseloopDumpProvider(self._data_dir))

    def default_provider(self) -> DataProvider:
        return CloseloopDumpProvider(self._data_dir)

    def normalize_symbol(self, raw: str) -> str:
        return normalize_cl_symbol(raw)

    def lot_size(self, symbol: str) -> int:
        return 100

    def universe(self) -> dict[str, str]:
        parquet = self._data_dir / "panel.parquet"
        if not parquet.is_file():
            inst_file = self._data_dir / "instruments" / "csi300.txt"
            alt = self._data_dir / "instruments" / "all.txt"
            path = inst_file if inst_file.is_file() else alt
            if not path.is_file():
                return {}
            names = []
            for ln in path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    names.append(ln.split("\t")[0].strip())
            return {n: n for n in names}
        panel = pd.read_parquet(parquet)
        instruments = list(panel.columns.get_level_values("instrument").unique())
        return {str(s): str(s) for s in instruments}

    def fetch_quote(self, symbol: str) -> Quote:
        canonical = self.normalize_symbol(symbol)
        try:
            return super().fetch_quote(canonical)
        except ValueError:
            raise
