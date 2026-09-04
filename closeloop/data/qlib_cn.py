"""Load a Qlib-shaped A-share dump.

When pyqlib is installed and calendars exist, prefer ``qlib.init`` + ``D.features``.
Otherwise (or on any qlib error) read ``panel.parquet``. Extra parquet fields such as
``industry`` / ``cap`` are merged onto the qlib OHLCV panel.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from closeloop.data.protocol import DEFAULT_FIELDS, DataPlane, default_data_dir, panel_from_fields


def _parse_calendar(path: Path) -> pd.DatetimeIndex:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return pd.DatetimeIndex(pd.to_datetime(lines), name="datetime")


def _parse_instruments(path: Path) -> tuple[str, ...]:
    names: list[str] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        names.append(ln.split("\t")[0].strip())
    return tuple(names)


class QlibCnDataPlane(DataPlane):
    def __init__(
        self,
        data_dir: Path | None = None,
        universe: str = "csi300",
        *,
        prefer_qlib: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.universe = universe
        self.prefer_qlib = bool(prefer_qlib)

    def calendar(self) -> pd.DatetimeIndex:
        return _parse_calendar(self.data_dir / "calendars" / "day.txt")

    def instruments(self) -> tuple[str, ...]:
        uni = self.data_dir / "instruments" / f"{self.universe}.txt"
        path = uni if uni.exists() else self.data_dir / "instruments" / "all.txt"
        return _parse_instruments(path)

    def _load_parquet(self, start: str, end: str) -> pd.DataFrame | None:
        parquet = self.data_dir / "panel.parquet"
        if not parquet.exists():
            return None
        panel = pd.read_parquet(parquet)
        panel.index = pd.DatetimeIndex(panel.index, name="datetime")
        return panel.loc[start:end]

    def _try_qlib_features(self, start: str, end: str, fields: tuple[str, ...]) -> pd.DataFrame | None:
        if not (self.data_dir / "calendars" / "day.txt").exists():
            return None
        try:
            return self._load_via_qlib(start, end, fields)
        except Exception:
            return None

    def load_panel(
        self,
        start: str,
        end: str,
        fields: tuple[str, ...] | None = None,
    ) -> pd.DataFrame:
        parquet_panel = self._load_parquet(start, end)
        qlib_fields = fields if fields is not None else DEFAULT_FIELDS
        qlib_panel = self._try_qlib_features(start, end, qlib_fields) if self.prefer_qlib else None
        if qlib_panel is not None:
            merged = qlib_panel
            if parquet_panel is not None:
                extra = set(parquet_panel.columns.get_level_values("field")) - set(
                    merged.columns.get_level_values("field")
                )
                if extra:
                    keep = [c for c in parquet_panel.columns if c[0] in extra]
                    merged = pd.concat([merged, parquet_panel.loc[:, keep]], axis=1).sort_index(axis=1)
            if fields is not None:
                keep = [c for c in merged.columns if c[0] in fields]
                return merged.loc[:, keep]
            return merged
        if parquet_panel is not None:
            if fields is None:
                return parquet_panel
            keep = [c for c in parquet_panel.columns if c[0] in fields]
            return parquet_panel.loc[:, keep]
        use_fields = fields if fields is not None else DEFAULT_FIELDS
        return self._load_via_qlib(start, end, use_fields)

    def _load_via_qlib(self, start: str, end: str, fields: tuple[str, ...]) -> pd.DataFrame:
        try:
            import qlib
            from qlib.data import D
        except ImportError as exc:
            raise FileNotFoundError(
                f"no panel.parquet under {self.data_dir} and pyqlib is not installed"
            ) from exc
        qlib.init(provider_uri=str(self.data_dir), region="cn")
        inst = list(self.instruments())
        qfields = [f"${f}" for f in fields]
        raw = D.features(inst, qfields, start_time=start, end_time=end)
        # Qlib returns MultiIndex (instrument, datetime) × fields
        packed: dict[str, pd.DataFrame] = {}
        for f, qf in zip(fields, qfields):
            col = raw[qf].unstack(level=0)
            packed[f] = col
        return panel_from_fields(packed)
