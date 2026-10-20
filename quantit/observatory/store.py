"""Atomic cached observations; failed refreshes retain last successful data."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from .catalog import SERIES


def default_root():
    return Path(os.environ.get("QUANTIT_OBSERVATORY_ROOT", str(Path.home() / ".quantit/observatory")))


def utcnow():
    return datetime.now(timezone.utc)


def atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as stream:
        json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
        temporary = Path(stream.name)
    temporary.replace(path)


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def archive(root, payload, extension):
    checksum = hashlib.sha256(payload).hexdigest()
    path = root / "raw" / f"{checksum}.{extension}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as stream:
            stream.write(payload)
            temporary = Path(stream.name)
        temporary.replace(path)
    return {"sha256": checksum, "file": str(path.relative_to(root))}


def save_series(root, key, values, evidence):
    points = [{"date": str(day.date()), "value": None if pd.isna(value) else float(value)}
              for day, value in values.items()]
    if sum(p["value"] is not None for p in points) < 2:
        raise ValueError("No usable series")
    path = root / "series" / f"{key}.json"
    previous = read(path, {})
    before = [p for p in previous.get("observations", []) if p["value"] is not None]
    after = [p for p in points if p["value"] is not None]
    if before and (after[-1]["date"] < before[-1]["date"] or after[0]["date"] > before[0]["date"]):
        raise ValueError("Source history shrank; retaining the more complete successful cache")
    result = {"id": key, "observations": points, "fetched_at": utcnow().isoformat(),
              "last_attempt": utcnow().isoformat(), "error": None, "evidence": evidence}
    atomic(path, result)
    return result


def failed_series(root, key, error):
    path = root / "series" / f"{key}.json"
    previous = read(path, {"id": key, "observations": [], "fetched_at": None})
    atomic(path, {**previous, "last_attempt": utcnow().isoformat(), "error": str(error)[:350]})


def summary(root, key, now=None):
    meta = SERIES[key]
    data = read(root / "series" / f"{key}.json", {})
    points = data.get("observations", [])
    valid = [p for p in points if p["value"] is not None]
    last, prior = (valid[-1] if valid else None), (valid[-2] if len(valid) > 1 else None)
    # "Prior period" refers to the adjacent statistical period, not the last
    # non-null observation across a gap.
    if last:
        index = next(i for i in range(len(points) - 1, -1, -1) if points[i]["date"] == last["date"])
        prior = points[index - 1] if index > 0 and points[index - 1]["value"] is not None else None
    age = None
    if data.get("fetched_at"):
        age = ((now or utcnow()) - datetime.fromisoformat(data["fetched_at"])).total_seconds()
    source_notice = (data.get("evidence") or {}).get("source_notice")
    observation_age = ((now or utcnow()).date() - pd.Timestamp(last["date"]).date()).days if last else None
    observation_stale = observation_age is None or observation_age > {"M": 100, "Q": 200, "Y": 800, "D": 35}[meta["frequency"]]
    return {**meta, "latest": last, "previous": prior,
            "change": last["value"] - prior["value"] if last and prior else None,
            "first_date": valid[0]["date"] if valid else None,
            "last_date": last["date"] if last else None, "count": len(valid),
            "missing_periods": len(points) - len(valid),
            "fetched_at": data.get("fetched_at"), "error": data.get("error"),
            "source_notice": source_notice, "download_url": (data.get("evidence") or {}).get("download_url"),
            "observation_stale": observation_stale,
            "cache_stale": age is None or age > 86400,
            "state": "unavailable" if not valid else "cached" if data.get("error") or source_notice or age is None or age > 86400 or observation_stale else "ready"}


def series_view(root, key, years=5, view="level", now=None):
    meta = summary(root, key, now)
    data = read(root / "series" / f"{key}.json", {})
    rows = data.get("observations", [])
    values = pd.Series([r["value"] for r in rows], index=pd.to_datetime([r["date"] for r in rows]), dtype=float)
    unit = meta["unit"]
    label = meta["name"]
    if view == "change":
        values = values.diff()
        unit = "百分点" if unit == "%" else unit
        label = "较上期变化"
    elif view == "volatility":
        if meta["kind"] == "factor":
            # Values are percentage returns, so output is already percent.
            values = values.rolling(12, min_periods=12).std(ddof=1) * np.sqrt(12)
            label, unit = "12 个月滚动年化波动率", "%"
        elif meta["kind"] == "local_factor":
            values = values.rolling(21, min_periods=21).std(ddof=1)
            label, unit = "21 个交易日 IC 标准差（不年化）", "IC"
        else:
            raise ValueError("Volatility view is only defined for factors")
    elif view != "level":
        raise ValueError("Unknown view")
    today = pd.Timestamp(now or utcnow()).tz_localize(None).normalize()
    requested_start = today - pd.DateOffset(years=years) if years else None
    full_first = values.first_valid_index()
    values = values.loc[values.index <= today]
    if requested_start is not None:
        values = values.loc[values.index >= requested_start]
    # Long-history coverage is based on raw data availability, not 12-month
    # warmup requirements or the first point surviving a view filter.
    coverage_short = bool(years and (not meta["first_date"] or pd.Timestamp(meta["first_date"]) > requested_start))
    observations = [{"date": str(d.date()), "value": None if pd.isna(v) else float(v)} for d, v in values.items()]
    return {"series": meta, "observations": observations, "view": view, "view_label": label, "unit": unit,
            "years": years, "requested_start": str(requested_start.date()) if requested_start is not None else None,
            "coverage_short": coverage_short,
            "view_first_date": str(full_first.date()) if full_first is not None else None,
            "evidence": data.get("evidence")}
