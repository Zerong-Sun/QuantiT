"""Bounded public-source downloads and schema-checked parsers."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import io
import json
import re
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pandas as pd
import requests

from .catalog import FRENCH_URL

FRENCH_SNAPSHOT_URL = (
    "https://raw.githubusercontent.com/anibitri/portfolio_construction/"
    "e2a06f518e561f1ba73023e3a2c89d37a3b7b59d/data/F-F_Research_Data_5_Factors_2x3.csv"
)
FRENCH_SNAPSHOT_SHA256 = "b1b74d178ced4491025e69de6724fb42dd358dbd715134b7d9b147906c30fc69"


def get_bytes(url, params=None):
    response = requests.get(url, params=params, timeout=(12, 30))
    response.raise_for_status()
    if len(response.content) > 8_000_000:
        raise ValueError("Source response exceeds 8 MB")
    return response.content


def download_dataset(provider, dataset):
    if provider == "FRED":
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={dataset}"
        return get_bytes(url), "csv", {"download_url": url}
    if provider == "东方财富宏观数据":
        data = get_bytes("https://datacenter-web.eastmoney.com/api/data/v1/get",
                         {"reportName": dataset, "columns": "ALL", "pageNumber": 1, "pageSize": 2000,
                          "sortColumns": "REPORT_DATE", "sortTypes": -1, "source": "WEB", "client": "WEB"})
        result = json.loads(data).get("result") or {}
        if int(result.get("pages", 1)) > 1:
            raise ValueError("Provider history exceeds one page; refusing truncated history")
        return data, "json", {"download_url": "https://datacenter-web.eastmoney.com/api/data/v1/get"}
    if provider == "World Bank WDI":
        url = f"https://api.worldbank.org/v2/country/CHN/indicator/{dataset}"
        return get_bytes(url, {"format": "json", "per_page": 1000}), "json", {"download_url": url}
    if dataset == "ff5":
        try:
            return get_bytes(FRENCH_URL), "zip", {"download_url": FRENCH_URL}
        except requests.RequestException:
            # A pinned, visibly labelled research snapshot is preferable to a
            # fabricated update or an unverified moving third-party mirror.
            payload = get_bytes(FRENCH_SNAPSHOT_URL)
            if hashlib.sha256(payload).hexdigest() != FRENCH_SNAPSHOT_SHA256:
                raise ValueError("French historical mirror checksum mismatch")
            return payload, "csv", {
                "download_url": FRENCH_SNAPSHOT_URL,
                "source_notice": "官方下载暂不可达，当前为公开研究仓库中的固定历史镜像，仅截至 2026-02。不是最新官方数据；后台会重试官方来源。",
            }
    raise ValueError("Unsupported data provider")


def french_frame(payload):
    if payload.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            if len(names) != 1 or archive.getinfo(names[0]).file_size > 8_000_000:
                raise ValueError("Unexpected French archive")
            lines = archive.read(names[0]).decode("utf-8-sig").splitlines()
    else:
        lines = payload.decode("utf-8-sig").splitlines()
    header = next((i for i, line in enumerate(lines) if "Mkt-RF" in line and "SMB" in line), None)
    if header is None:
        raise ValueError("French monthly header missing")
    rows = []
    for line in lines[header + 1:]:
        if re.match(r"^\s*\d{6}\s*,", line):
            rows.append(line)
        elif rows:
            break  # annual section is a different series, never concatenate it
    frame = pd.read_csv(io.StringIO(lines[header] + "\n" + "\n".join(rows)), index_col=0)
    frame.columns = frame.columns.str.strip()
    frame.index = pd.to_datetime(frame.index.astype(str), format="%Y%m")
    return frame.replace([-99.99, -999], np.nan)


def normalize(values, frequency, now=None):
    """Keep missing periods explicit; reject duplicates, infinities and future periods."""
    now = pd.Timestamp(now or datetime.now(timezone.utc)).tz_localize(None).normalize()
    result = pd.Series(pd.to_numeric(values, errors="coerce").to_numpy(), index=pd.to_datetime(values.index))
    if result.index.isna().any() or np.isinf(result.to_numpy()).any():
        raise ValueError("Invalid dates or infinite observations")
    if frequency in {"M", "Q", "Y"}:
        result.index = result.index.to_period(frequency).to_timestamp(how="end").normalize()
    else:
        result.index = result.index.normalize()
    result = result.sort_index()
    if result.index.has_duplicates:
        raise ValueError("Duplicate statistical periods")
    result = result.loc[result.index <= now]
    if frequency in {"M", "Q", "Y"} and len(result):
        periods = pd.period_range(result.index.min(), result.index.max(), freq=frequency)
        result = result.reindex(periods.to_timestamp(how="end").normalize())
    if result.notna().sum() < 2:
        raise ValueError("Insufficient finite historical observations")
    return result


def parse_series(meta, payload, now=None):
    provider, dataset = meta["provider"], meta["dataset"]
    if provider == "FRED":
        frame = pd.read_csv(io.BytesIO(payload), na_values=["."])
        if dataset not in frame or "observation_date" not in frame:
            raise ValueError("Unexpected FRED schema")
        raw = pd.Series(frame[dataset].to_numpy(), index=frame.observation_date)
    elif provider == "东方财富宏观数据":
        rows = (json.loads(payload).get("result") or {}).get("data")
        if not rows or any(meta["field"] not in r or "REPORT_DATE" not in r for r in rows):
            raise ValueError("Unexpected China macro schema")
        raw = pd.Series([r[meta["field"]] for r in rows], index=[r["REPORT_DATE"] for r in rows])
    elif provider == "World Bank WDI":
        data = json.loads(payload)
        if not isinstance(data, list) or len(data) != 2 or int(data[0].get("pages", 1)) != 1:
            raise ValueError("Unexpected World Bank schema/pagination")
        rows = data[1] or []
        raw = pd.Series([r["value"] for r in rows], index=[f'{r["date"]}-01-01' for r in rows])
    elif dataset == "ff5":
        raw = french_frame(payload)[meta["field"]]
    else:
        raise ValueError("Unknown parser")
    series = normalize(raw, meta["frequency"], now)
    if meta["transform"] == "diff":
        series = series.diff()  # calendar reindex above prevents crossing missing months
    elif meta["transform"] == "yoy":
        series = (series / series.shift(12) - 1) * 100
    return series.replace([np.inf, -np.inf], np.nan).loc[lambda x: x.index >= x.first_valid_index()]


def safe_url(raw):
    try:
        parts = urlsplit(raw.strip())
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def parse_news(payload, source_id, source, now=None):
    now = now or datetime.now(timezone.utc)
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("DTD/entity declarations are not accepted in feeds")
    root = ET.fromstring(payload)
    result = []
    for item in root.findall(".//item"):
        title = html.unescape(re.sub("<[^>]+>", "", item.findtext("title") or "")).strip()
        url = safe_url(item.findtext("link") or "")
        if not title or not url:
            continue
        published = None
        try:
            value = parsedate_to_datetime(item.findtext("pubDate") or "")
            if value.tzinfo is None:
                # An unspecified timezone must not become a fabricated recent event.
                value = None
            if value:
                value = value.astimezone(timezone.utc)
                if value > now:
                    continue
                published = value.isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
        tags = []
        for tag, pattern in [
            ("政策与利率", r"interest rate|federal reserve|monetary|利率|央行|降息|加息|货币政策"),
            ("经济数据", r"payroll|inflation|unemployment|GDP|CPI|PMI|非农|通胀|经济数据|就业"),
            ("突发风险线索", r"\bwar\b|attack|earthquake|sanction|crisis|冲突|袭击|地震|制裁|危机|关税"),
        ]:
            if re.search(pattern, title, re.I):
                tags.append(tag)
        result.append({"id": hashlib.sha256(url.encode()).hexdigest()[:20], "title": title[:400],
                       "url": url, "source_id": source_id, "source": source["name"],
                       "region": source["region"], "published_at": published, "tags": tags or ["市场动态"]})
    if not result:
        raise ValueError("Feed contains no usable articles")
    return result
