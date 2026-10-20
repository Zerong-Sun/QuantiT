"""Versioned raw prices/actions for isolated daily paper histories."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from quantit.data.macro import DEFAULT_MACRO_SYMBOLS
from quantit.markets.assets import asset_class
from quantit.paper.books import venue_of
from quantit.paper.recovery import BOOK_SYMBOLS, REFERENCES


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(stream.name)
    temporary.replace(path)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def cn_symbol(instrument: str) -> str:
    return instrument[2:] + (".SS" if instrument.startswith("SH") else ".SZ")


def request_symbols(panel: pd.DataFrame) -> dict[str, str]:
    symbols = {}
    for book, names in BOOK_SYMBOLS.items():
        for symbol in names:
            if asset_class(venue_of(book), symbol) in {"equity", "etf"}:
                symbols[symbol] = venue_of(book)
    symbols.update({s: venue for venue, s in REFERENCES.items()})
    symbols.update({cn_symbol(s): "cn" for s in panel["close"].columns})
    symbols.update({s: "macro" for s in DEFAULT_MACRO_SYMBOLS.values()})
    return symbols


def split_adjusted_from_nominal(frame: pd.DataFrame, events: list[dict]) -> pd.DataFrame:
    """Convert independently sourced nominal OHLCV into the bundle convention."""
    result = frame[["open", "high", "low", "close", "volume"]].astype(float).copy()
    result["stock_splits"] = 0.0
    result["dividends"] = 0.0
    for event in events:
        day = pd.Timestamp(event["ex_date"])
        if day in result.index:
            result.loc[day, "stock_splits"] = event["ratio"]
    splits = result.stock_splits.replace(0, 1)
    future = splits.iloc[::-1].cumprod().iloc[::-1] / splits
    result.loc[:, ["open", "high", "low", "close"]] = result[["open", "high", "low", "close"]].div(future, axis=0)
    result["volume"] *= future
    result["adj_close"] = result.close
    return result


def verified_etf(root: Path, symbol: str, yahoo: pd.DataFrame, begin: str, finish: str):
    events = json.loads(Path(__file__).with_name("history_actions.json").read_text())["events"].get(symbol)
    if not events:
        return yahoo, None
    if yahoo.get("dividends", pd.Series(dtype=float)).fillna(0).ne(0).any():
        raise ValueError("Known ETF correction now has cash dividends; action convention needs review")
    import akshare as ak
    source = root / "source" / f"{symbol}-tencent-nominal.parquet"
    source.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        actual = pd.read_parquet(source)
    else:
        code = ("sh" if symbol.endswith(".SS") else "sz") + symbol[:6]
        actual = ak.stock_zh_a_hist_tx(symbol=code, start_date=begin.replace("-", ""),
                                     end_date=finish.replace("-", ""), adjust="", timeout=20)
        actual = actual.set_index(pd.to_datetime(actual["date"]))[["open", "high", "low", "close", "volume"]]
        actual.index.name = "Date"
        actual = actual[~actual.index.duplicated()].sort_index()
        if actual.empty:
            raise ValueError(f"Independent nominal feed missing: {symbol}")
        actual.to_parquet(source)
    if actual.index.min() > yahoo.index.min() or actual.index.max() < yahoo.index.max():
        raise ValueError(f"Independent feed does not cover Yahoo snapshot: {symbol}")
    return split_adjusted_from_nominal(actual, events), {
        "provider": "Tencent unadjusted OHLCV via AkShare", "file": str(source.relative_to(root)),
        "sha256": digest(source), "actions": events,
    }


def quality_issues(frame: pd.DataFrame, venue: str) -> list[dict]:
    """Hard data-contract failures; never repair price jumps by guessing a ratio."""
    issues = []
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        issues.append({"day": str(frame.index.min().date()), "reason": "Duplicate or unsorted dates"})
    prices = frame[["open", "high", "low", "close"]]
    invalid = (~np.isfinite(prices)).any(axis=1) | (prices <= 0).any(axis=1)
    for day in frame.index[invalid]:
        issues.append({"day": str(day.date()), "reason": "Invalid OHLC"})
    envelope = (frame.high + 1e-6 < prices[["open", "close"]].max(axis=1))
    envelope |= (frame.low - 1e-6 > prices[["open", "close"]].min(axis=1))
    for day in frame.index[envelope & ~invalid]:
        # Some feeds exclude opening auctions from the high/low range. Keep the
        # observed open/close; surface the inconsistency rather than invent bars.
        issues.append({"day": str(day.date()), "reason": "Open/close outside reported daily range",
                       "severity": "warning"})
    if venue == "cn":
        nominal = nominal_prices(frame)
        splits = nominal.get("stock_splits", pd.Series(0, index=nominal.index)).fillna(0).replace(0, 1)
        reference = nominal.close.shift(1) / splits - nominal.get("dividends", 0)
        gap = nominal.open / reference - 1
        for day, value in gap[gap.abs() > .35].items():
            issues.append({"day": str(day.date()), "reason": f"Unexplained opening gap {value:.2%}"})
    return issues


def verify_cn_latest(root: Path, symbol: str, frame: pd.DataFrame):
    """Cross-check latest CN OHLC: Yahoo can combine a stale open with today's close."""
    import requests
    last = frame.index[-1]
    code = ("sh" if symbol.endswith(".SS") else "sz") + symbol[:6]
    source = root / "source" / f"{symbol}-latest-tencent.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        data = json.loads(source.read_text())
    else:
        response = requests.get("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
                                params={"param": f"{code},day,{last.date()},{last.date()},10,"}, timeout=20)
        response.raise_for_status()
        data = response.json()
        atomic_json(source, data)
    rows = data.get("data", {}).get(code, {}).get("day", [])
    row = next((r for r in rows if r[0] == str(last.date())), None)
    if row is None:
        if (rows and float(frame.volume.iloc[-1]) == 0
                and abs(float(rows[-1][2]) - float(frame.close.iloc[-1])) < .0051):
            return frame, {"day": str(last.date()), "provider": "Tencent last traded close; Yahoo zero volume",
                           "last_traded": rows[-1][0], "non_trading": True,
                           "file": str(source.relative_to(root)), "sha256": digest(source), "differences": {}}
        raise ValueError(f"No independent latest-session OHLC: {symbol}/{last.date()}")
    # Last session has no subsequent split, so nominal and split-adjusted units agree.
    result = frame.copy()
    values = dict(zip(("open", "close", "high", "low"), map(float, row[1:5])))
    if not all(np.isfinite(v) and v > 0 for v in values.values()):
        raise ValueError(f"Invalid independent latest-session prices: {symbol}")
    ratio = float(result.loc[last, "adj_close"] / result.loc[last, "close"])
    differences = {field: {"yahoo": float(frame.loc[last, field]), "tencent": value}
                   for field, value in values.items() if abs(frame.loc[last, field] - value) > .0051}
    for field, value in values.items():
        result.loc[last, field] = value
    result.loc[last, "adj_close"] = values["close"] * ratio
    return result, {"day": str(last.date()), "provider": "Tencent nominal OHLC; volume/actions retained",
                    "file": str(source.relative_to(root)), "sha256": digest(source), "differences": differences}


def download(root: Path, symbols: dict[str, str], start: str, end: str, workers: int = 4) -> dict:
    """Only Yahoo raw OHLCV + actions; do not silently replace with adjusted bars."""
    root.mkdir(parents=True, exist_ok=True)
    begin = str((pd.Timestamp(start) - pd.Timedelta(days=600)).date())
    finish = str((pd.Timestamp(end) + pd.Timedelta(days=1)).date())

    def one(item):
        import yfinance as yf

        symbol, venue = item
        filename = f"{symbol.replace('^', '_').replace('=', '_')}.parquet"
        path = root / filename
        try:
            if path.exists():
                frame = pd.read_parquet(path)
            else:
                frame = yf.Ticker(symbol).history(start=begin, end=finish, auto_adjust=False,
                                                  actions=True, timeout=15)
                if frame.empty:
                    raise ValueError("No raw history from provider")
                frame.columns = [str(c).lower().replace(" ", "_") for c in frame.columns]
                frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
                frame = frame[~frame.index.duplicated()].sort_index()
                frame.to_parquet(path)
            original_hash = digest(path)
            latest_check = None
            if venue == "cn":
                original = root / "source" / f"{symbol}-yahoo-original.parquet"
                original.parent.mkdir(parents=True, exist_ok=True)
                if not original.exists():
                    import shutil
                    shutil.copy2(path, original)
            frame, correction = verified_etf(root, symbol, frame, begin, end)
            if correction:
                original = root / "source" / f"{symbol}-yahoo-original.parquet"
                if not original.exists():
                    import shutil
                    shutil.copy2(path, original)
            if venue == "cn":
                frame, latest_check = verify_cn_latest(root, symbol, frame)
                frame.to_parquet(path)
            return symbol, {"venue": venue, "file": filename, "sha256": digest(path),
                            "first": str(frame.index.min().date()), "last": str(frame.index.max().date()),
                            "rows": len(frame), "original_sha256": original_hash,
                            "correction": correction, "latest_check": latest_check,
                            "quality_issues": quality_issues(frame, venue)}
        except Exception as exc:
            return symbol, {"venue": venue, "error": str(exc)}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        result = dict(pool.map(one, sorted(symbols.items())))
    metadata = {"requested_start": start, "requested_end": end, "provider": "Yahoo raw OHLCV/actions",
                "downloaded_at": datetime.now(timezone.utc).isoformat(), "symbols": result}
    atomic_json(root / "manifest.json", metadata)
    return metadata


def load_bundle(root: Path) -> tuple[dict, dict[str, pd.DataFrame]]:
    manifest = json.loads((root / "manifest.json").read_text())
    frames = {}
    for symbol, info in manifest["symbols"].items():
        if "file" in info:
            path = root / info["file"]
            if digest(path) != info["sha256"]:
                raise ValueError(f"Changed price snapshot: {symbol}")
            frames[symbol] = pd.read_parquet(path)
    return manifest, frames


def adjusted(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "adj_close" in frame:
        ratio = frame["adj_close"] / frame["close"]
        for col in ("open", "high", "low", "close"):
            result[col] = frame[col] * ratio
    return result


def nominal_prices(frame: pd.DataFrame) -> pd.DataFrame:
    """Undo Yahoo's split adjustment before applying split actions to held lots.

    Yahoo's auto_adjust=False still reports split-adjusted historical prices.
    Dividend entitlements are estimates in the provider's share convention.
    """
    result = frame.copy()
    splits = frame.get("stock_splits", pd.Series(0.0, index=frame.index)).fillna(0).replace(0, 1)
    future = splits.iloc[::-1].cumprod().iloc[::-1] / splits
    for col in ("open", "high", "low", "close", "dividends"):
        if col in result:
            result[col] *= future
    # Historical share volume is expressed in the inverse share convention.
    result["volume"] /= future
    return result
