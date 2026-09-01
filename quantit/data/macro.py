"""Macro time-series loader (Yahoo closes, aligned to a trading calendar)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from quantit.data.loader import DataLoader

DEFAULT_MACRO_SYMBOLS: dict[str, str] = {
    "dxy": "DX-Y.NYB",
    "us10y": "^TNX",
    "cny": "CNY=X",
    "hkd": "HKD=X",
    "nasdaq": "^IXIC",
    "gold": "GC=F",
}


def load_southbound_csv(path: str | Path) -> pd.Series:
    """Load optional southbound net flow. CSV columns: date, net_flow."""
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    if "date" not in cols or "net_flow" not in cols:
        raise ValueError("Southbound CSV must have columns 'date' and 'net_flow'")
    out = df.rename(columns={cols["date"]: "date", cols["net_flow"]: "net_flow"})
    series = pd.Series(
        out["net_flow"].to_numpy(),
        index=pd.to_datetime(out["date"]),
        name="southbound",
    )
    return series.sort_index()


class MacroLoader:
    """Fetch named macro closes via the shared OHLCV loader."""

    def __init__(self, loader: DataLoader | None = None) -> None:
        self.loader = loader or DataLoader()

    def load(
        self,
        start: str | datetime,
        end: str | datetime,
        symbols: dict[str, str] | None = None,
        calendar: pd.DatetimeIndex | None = None,
        skip_missing: bool = True,
    ) -> pd.DataFrame:
        """Return a wide DataFrame of close prices (one column per macro key).

        Rows are aligned to ``calendar`` (typically HK equity sessions) and
        forward-filled. Missing Yahoo symbols are skipped when ``skip_missing``.
        """
        mapping = symbols or DEFAULT_MACRO_SYMBOLS
        columns: dict[str, pd.Series] = {}
        skipped: list[str] = []
        for name, yahoo in mapping.items():
            try:
                df = self.loader.load(yahoo, start, end)
            except (ValueError, Exception):
                if skip_missing:
                    skipped.append(yahoo)
                    continue
                raise
            if df.empty or "close" not in df.columns:
                skipped.append(yahoo)
                continue
            columns[name] = df["close"].rename(name)

        if not columns:
            frame = pd.DataFrame()
        else:
            frame = pd.concat(columns.values(), axis=1).sort_index()

        if calendar is not None and not calendar.empty:
            frame = frame.reindex(frame.index.union(calendar)).sort_index()
            frame = frame.ffill()
            frame = frame.reindex(calendar)

        frame.attrs["skipped"] = skipped
        return frame
