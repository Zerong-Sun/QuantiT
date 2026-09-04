"""Write a Qlib-shaped dump from a panel or from A-share CSVs.

Production ingest uses AkShare CSI300 constituents (network). Tests use --from-csv.
This module never reads quantit CN ETF CSV or Yahoo US bars.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from closeloop.data.protocol import DEFAULT_FIELDS, default_data_dir, panel_from_fields

_DATE_CANDIDATES = ("date", "datetime", "trade_date", "日期")
_MAP = {
    "open": ("open", "开盘"),
    "high": ("high", "最高"),
    "low": ("low", "最低"),
    "close": ("close", "收盘"),
    "volume": ("volume", "vol", "成交量"),
    "vwap": ("vwap", "avg", "平均"),
}


def _pick_col(df: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def _frame_from_table(df: pd.DataFrame) -> pd.DataFrame:
    date_col = _pick_col(df, _DATE_CANDIDATES)
    if date_col is None:
        raise ValueError("table has no date column")
    out = pd.DataFrame(index=pd.to_datetime(df[date_col]))
    out.index.name = "datetime"
    for field, aliases in _MAP.items():
        col = _pick_col(df, aliases)
        if col is not None:
            out[field] = pd.to_numeric(df[col], errors="coerce").to_numpy()
    if "close" not in out.columns:
        raise ValueError("table has no close column")
    for needed in ("open", "high", "low"):
        if needed not in out.columns:
            out[needed] = out["close"]
    if "volume" not in out.columns:
        out["volume"] = 1.0
    if "vwap" not in out.columns:
        out["vwap"] = (out["high"] + out["low"] + out["close"]) / 3.0
    return out.sort_index()


def read_symbol_csv(path: Path) -> pd.DataFrame:
    return _frame_from_table(pd.read_csv(path))


def panel_from_csv_dir(csv_dir: Path) -> pd.DataFrame:
    csv_dir = Path(csv_dir)
    frames: dict[str, dict[str, pd.Series]] = {f: {} for f in DEFAULT_FIELDS}
    paths = sorted(csv_dir.glob("*.csv"))
    if not paths:
        raise FileNotFoundError(f"no CSV files in {csv_dir}")
    for path in paths:
        symbol = path.stem.upper()
        bar = read_symbol_csv(path)
        for field in DEFAULT_FIELDS:
            frames[field][symbol] = bar[field]
    packed = {name: pd.DataFrame(cols).sort_index() for name, cols in frames.items()}
    return panel_from_fields(packed)


def attach_cap(panel: pd.DataFrame) -> pd.DataFrame:
    """Dollar-volume proxy: close * volume. Not official free-float market cap."""
    from closeloop.data.protocol import field_frame

    if "cap" in panel.columns.get_level_values("field"):
        return panel
    cap = field_frame(panel, "close") * field_frame(panel, "volume")
    cap.columns = pd.MultiIndex.from_product([["cap"], cap.columns], names=["field", "instrument"])
    out = pd.concat([panel, cap], axis=1).sort_index(axis=1)
    out.index = pd.DatetimeIndex(out.index, name="datetime")
    return out


def load_industry_map(path: Path) -> dict[str, float]:
    """Read instrument → 申万一级 id (or any numeric industry code) from a CSV/TSV."""
    path = Path(path)
    sep = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
    df = pd.read_csv(path, sep=sep)
    if df.empty:
        return {}
    cols = {str(c).strip().lower(): c for c in df.columns}
    inst_col = next((cols[k] for k in ("instrument", "symbol", "code", "ticker") if k in cols), None)
    ind_col = next(
        (cols[k] for k in ("industry", "industry_id", "sw1", "sw_l1", "id") if k in cols),
        None,
    )
    if inst_col is None or ind_col is None:
        if df.shape[1] < 2:
            raise ValueError("industry_map needs instrument and industry columns")
        inst_col, ind_col = df.columns[0], df.columns[1]
    mapping: dict[str, float] = {}
    for _, row in df.iterrows():
        mapping[str(row[inst_col]).strip()] = float(row[ind_col])
    return mapping


def attach_industry(panel: pd.DataFrame, mapping: dict[str, float]) -> pd.DataFrame:
    from closeloop.data.protocol import field_frame

    close = field_frame(panel, "close")
    industry = pd.DataFrame(index=close.index, columns=close.columns, dtype=float)
    for inst in close.columns:
        industry[inst] = float(mapping.get(str(inst), 0.0))
    industry.columns = pd.MultiIndex.from_product(
        [["industry"], industry.columns], names=["field", "instrument"]
    )
    out = pd.concat([panel, industry], axis=1).sort_index(axis=1)
    out.index = pd.DatetimeIndex(out.index, name="datetime")
    return out


def write_qlib_layout(panel: pd.DataFrame, dest: Path, universe: str = "csi300") -> Path:
    """Write calendars, instruments, float32 bins, and panel.parquet."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "calendars").mkdir(exist_ok=True)
    (dest / "instruments").mkdir(exist_ok=True)
    (dest / "features").mkdir(exist_ok=True)

    dates = pd.DatetimeIndex(panel.index).strftime("%Y-%m-%d")
    (dest / "calendars" / "day.txt").write_text("\n".join(dates.tolist()) + "\n", encoding="utf-8")

    instruments = list(panel.columns.get_level_values("instrument").unique())
    start, end = dates[0], dates[-1]
    lines = [f"{inst}\t{start}\t{end}" for inst in instruments]
    text = "\n".join(lines) + "\n"
    (dest / "instruments" / "all.txt").write_text(text, encoding="utf-8")
    (dest / "instruments" / f"{universe}.txt").write_text(text, encoding="utf-8")

    panel.to_parquet(dest / "panel.parquet")

    fields = list(panel.columns.get_level_values("field").unique())
    for inst in instruments:
        inst_dir = dest / "features" / inst
        inst_dir.mkdir(exist_ok=True)
        for field in fields:
            series = panel[(field, inst)].reindex(panel.index)
            arr = series.to_numpy(dtype=np.float32)
            (inst_dir / f"{field}.day.bin").write_bytes(arr.tobytes())
    return dest


def _to_qlib_symbol(code: str) -> str:
    digits = "".join(ch for ch in str(code) if ch.isdigit())[-6:].zfill(6)
    if digits.startswith("6"):
        return f"SH{digits}"
    return f"SZ{digits}"


def fetch_csi300_panel(
    start: str,
    end: str,
    *,
    limit: int | None = None,
    raw_dir: Path | None = None,
    sleep_s: float = 0.15,
) -> pd.DataFrame:
    """AkShare CSI300 members + daily bars. Network only; not used in CI."""
    import time

    import akshare as ak

    cons = ak.index_stock_cons_csindex(symbol="000300")
    code_col = None
    for col in cons.columns:
        text = str(col)
        if "代码" in text or str(col).lower() == "code":
            code_col = col
            break
    if code_col is None:
        raise RuntimeError(f"unexpected CSI300 columns: {list(cons.columns)}")
    start_n = start.replace("-", "")
    end_n = end.replace("-", "")
    codes = list(cons[code_col].astype(str))
    if limit is not None:
        codes = codes[: max(1, int(limit))]
    if raw_dir is not None:
        Path(raw_dir).mkdir(parents=True, exist_ok=True)
    fields: dict[str, dict[str, pd.Series]] = {f: {} for f in DEFAULT_FIELDS}
    for i, code in enumerate(codes):
        digits = "".join(ch for ch in str(code) if ch.isdigit())[-6:].zfill(6)
        symbol = _to_qlib_symbol(digits)
        cache = Path(raw_dir) / f"{symbol}.csv" if raw_dir is not None else None
        if cache is not None and cache.exists():
            bar = read_symbol_csv(cache)
        else:
            hist = ak.stock_zh_a_hist(
                symbol=digits,
                period="daily",
                start_date=start_n,
                end_date=end_n,
                adjust="qfq",
            )
            if hist is None or hist.empty:
                continue
            bar = _frame_from_table(hist)
            if cache is not None:
                out = bar.reset_index()
                out.to_csv(cache, index=False)
            if sleep_s:
                time.sleep(sleep_s)
        for field in DEFAULT_FIELDS:
            if field in bar.columns:
                fields[field][symbol] = bar[field]
        _ = i
    packed = {name: pd.DataFrame(cols).sort_index() for name, cols in fields.items() if cols}
    if not packed or "close" not in packed:
        raise RuntimeError("AkShare returned no CSI300 bars")
    return panel_from_fields(packed)


def ingest(
    *,
    dest: Path | None = None,
    universe: str = "csi300",
    start: str = "2018-01-01",
    end: str = "2024-12-31",
    from_csv: Path | None = None,
    limit: int | None = None,
    add_cap: bool = True,
    industry_map: dict[str, float] | None = None,
    industry_map_path: Path | None = None,
) -> Path:
    dest = Path(dest) if dest is not None else default_data_dir()
    raw_dir = dest / "raw"
    if from_csv is not None:
        panel = panel_from_csv_dir(Path(from_csv))
        raw_dir.mkdir(parents=True, exist_ok=True)
        for src in Path(from_csv).glob("*.csv"):
            target = raw_dir / src.name
            if not target.exists():
                target.write_bytes(src.read_bytes())
    else:
        panel = fetch_csi300_panel(start, end, limit=limit, raw_dir=raw_dir)
    if add_cap:
        panel = attach_cap(panel)
    if industry_map_path is not None:
        industry_map = load_industry_map(Path(industry_map_path))
    if industry_map:
        panel = attach_industry(panel, industry_map)
    return write_qlib_layout(panel, dest, universe=universe)
