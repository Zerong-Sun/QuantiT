"""Temporal, numerical and cache invariants for the observation-only module."""
from datetime import datetime, timezone
import hashlib
import io
import json
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import pytest

from quantit.api.observatory import attach_observatory_routes
from quantit.observatory.catalog import SERIES
from quantit.observatory.service import ObservatoryWorker
from quantit.observatory.sources import french_frame, normalize, parse_news, parse_series
from quantit.observatory.store import atomic, failed_series, read, save_series, series_view, summary

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def test_payroll_is_monthly_change_and_does_not_bridge_missing_months():
    payload = b"observation_date,PAYEMS\n2026-05-01,1000\n2026-06-01,1100\n2026-08-01,1200\n2026-09-01,1250\n"
    result = parse_series(SERIES["us_payroll"], payload, NOW)
    assert result.loc["2026-06-30"] == 100
    assert pd.isna(result.loc["2026-07-31"]) and pd.isna(result.loc["2026-08-31"])
    assert result.loc["2026-09-30"] == 50


def test_cpi_yoy_uses_exact_year_ago_and_keeps_zero_growth():
    payload = b"observation_date,CPIAUCNS\n2025-07-01,100\n2025-08-01,110\n2026-07-01,102\n2026-08-01,110\n2026-09-01,120\n"
    result = parse_series(SERIES["us_cpi"], payload, NOW)
    assert result.loc["2026-07-31"] == pytest.approx(2)
    assert result.loc["2026-08-31"] == 0
    assert pd.isna(result.loc["2026-09-30"])


def test_china_ppi_uses_growth_field_not_index_base():
    data = {"result": {"data": [
        {"REPORT_DATE": "2026-08-01", "BASE": 104, "BASE_SAME": 4},
        {"REPORT_DATE": "2026-09-01", "BASE": 105, "BASE_SAME": 5},
    ]}}
    result = parse_series(SERIES["cn_ppi"], json.dumps(data).encode(), NOW)
    assert result.tolist() == [4, 5]


def test_future_periods_are_not_published_as_current_observations():
    values = pd.Series([1, 2, 99], index=["2026-08-01", "2026-09-01", "2026-10-01"])
    result = normalize(values, "M", NOW)
    assert result.index[-1] == pd.Timestamp("2026-09-30")
    assert result.tolist() == [1, 2]


@pytest.mark.parametrize("dates,values", [
    (["2026-07-01", "2026-07-15"], [1, 2]),
    (["2026-07-01", "2026-08-01"], [1, float("inf")]),
])
def test_invalid_periods_fail_closed(dates, values):
    with pytest.raises(ValueError):
        normalize(pd.Series(values, index=dates), "M", NOW)


def test_world_bank_annual_series_remains_annual_and_filters_uncompleted_year():
    payload = json.dumps([{"pages": 1}, [
        {"date": "2026", "value": 99}, {"date": "2025", "value": 5},
        {"date": "2024", "value": 4}, {"date": "2023", "value": None},
    ]]).encode()
    result = parse_series(SERIES["cn_gdp_annual"], payload, NOW)
    assert result.index[-1] == pd.Timestamp("2025-12-31")
    assert result.iloc[-1] == 5


def test_french_monthly_parser_excludes_annual_table_and_missing_sentinels():
    text = "Notes\n,Mkt-RF,SMB,HML,RMW,CMA,RF\n196307,1,2,3,4,5,.1\n196308,-99.99,3,4,5,6,.1\n\nAnnual Factors\n1963,90,90,90,90,90,1\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data.csv", text)
    for payload in (text.encode(), buffer.getvalue()):
        frame = french_frame(payload)
        assert len(frame) == 2
        assert frame.loc["1963-07-01", "Mkt-RF"] == 1
        assert pd.isna(frame.loc["1963-08-01", "Mkt-RF"])


def test_long_window_does_not_invent_data_or_replace_null_with_zero(tmp_path):
    dates = pd.date_range("2025-01-31", periods=15, freq=pd.offsets.MonthEnd())
    save_series(tmp_path, "cn_cpi", pd.Series([0, np.nan] + list(range(13)), index=dates), {})
    result = series_view(tmp_path, "cn_cpi", 50, now=NOW)
    assert result["coverage_short"] is True
    assert result["observations"][0]["value"] == 0
    assert result["observations"][1]["value"] is None
    assert result["observations"][0]["date"] == "2025-01-31"
    assert result["requested_start"] == "1976-10-20"


def test_rolling_factor_volatility_uses_full_warmup_before_window_filter(tmp_path):
    dates = pd.date_range("2019-01-31", periods=84, freq=pd.offsets.MonthEnd())
    values = pd.Series(np.arange(84) % 5 - 2, index=dates, dtype=float)
    save_series(tmp_path, "ff_market", values, {})
    result = series_view(tmp_path, "ff_market", 5, "volatility", NOW)
    first = pd.Timestamp(result["observations"][0]["date"])
    expected = values.loc[:first].tail(12).std(ddof=1) * np.sqrt(12)
    assert result["observations"][0]["value"] == pytest.approx(expected)
    assert result["unit"] == "%"
    all_data = series_view(tmp_path, "ff_market", 0, "volatility", NOW)["observations"]
    assert all(p["value"] is None for p in all_data[:11])


def test_local_ic_volatility_is_not_annualized(tmp_path):
    dates = pd.bdate_range("2026-08-01", periods=30)
    values = pd.Series(np.arange(30) / 100, index=dates)
    save_series(tmp_path, "local_alpha158_lgbm_h1", values, {})
    result = series_view(tmp_path, "local_alpha158_lgbm_h1", 5, "volatility", NOW)
    assert result["observations"][-1]["value"] == pytest.approx(values.tail(21).std())


def test_failed_refresh_keeps_values_and_detects_cache_expiry(tmp_path):
    values = pd.Series([3, 4], index=pd.to_datetime(["2025-01-31", "2025-02-28"]))
    save_series(tmp_path, "cn_cpi", values, {})
    path = tmp_path / "series/cn_cpi.json"
    old = read(path)
    old["fetched_at"] = "2025-03-01T00:00:00+00:00"
    atomic(path, old)
    failed_series(tmp_path, "cn_cpi", "provider offline")
    current = read(path)
    assert current["observations"] == old["observations"]
    assert current["fetched_at"] == old["fetched_at"]
    status = summary(tmp_path, "cn_cpi", NOW)
    assert status["state"] == "cached" and status["cache_stale"]
    assert status["observation_stale"] and status["error"] == "provider offline"


def test_older_fallback_cannot_overwrite_newer_official_history(tmp_path):
    values = pd.Series([1, 2, 3], index=pd.date_range("2026-06-30", periods=3, freq=pd.offsets.MonthEnd()))
    save_series(tmp_path, "ff_market", values, {})
    with pytest.raises(ValueError, match="shrank"):
        save_series(tmp_path, "ff_market", values.iloc[:-1], {"source_notice": "old mirror"})
    assert summary(tmp_path, "ff_market", NOW)["last_date"] == "2026-08-31"


def test_prior_period_does_not_skip_a_missing_value(tmp_path):
    values = pd.Series([1, np.nan, 3], index=pd.date_range("2026-06-30", periods=3, freq=pd.offsets.MonthEnd()))
    save_series(tmp_path, "cn_cpi", values, {})
    assert summary(tmp_path, "cn_cpi", NOW)["change"] is None


def test_news_sanitizes_links_titles_and_never_invents_publication_dates():
    xml = b"""<rss><channel>
    <item><title><![CDATA[<b>Rate cut &amp; inflation</b>]]></title><link>https://example.com/a</link><pubDate>Tue, 20 Oct 2026 10:00:00 +0000</pubDate></item>
    <item><title>Unsafe</title><link>javascript:alert(1)</link></item>
    <item><title>Malformed</title><link>http://[invalid</link></item>
    <item><title>Future</title><link>https://example.com/future</link><pubDate>Wed, 21 Oct 2026 10:00:00 +0000</pubDate></item>
    <item><title>No date</title><link>https://example.com/unknown</link></item>
    </channel></rss>"""
    rows = parse_news(xml, "fed", {"name": "Fed", "region": "US"}, NOW)
    assert len(rows) == 2 and rows[0]["title"] == "Rate cut & inflation"
    assert rows[1]["published_at"] is None
    assert "经济数据" in rows[0]["tags"]
    assert parse_news(xml, "fed", {"name": "Fed", "region": "US"}, NOW)[0]["id"] == rows[0]["id"]


def test_news_rejects_xml_entity_declarations():
    with pytest.raises(ValueError, match="DTD"):
        parse_news(b'<!DOCTYPE a [<!ENTITY ext SYSTEM "file:///etc/passwd">]><rss/>',
                   "fed", {"name": "Fed", "region": "US"}, NOW)


def test_cached_api_validates_ranges_and_exports_nulls(tmp_path):
    save_series(tmp_path, "cn_cpi", pd.Series([1, np.nan, 0], index=pd.date_range("2026-06-30", periods=3, freq=pd.offsets.MonthEnd())), {})
    worker = ObservatoryWorker(tmp_path)
    app = FastAPI()
    attach_observatory_routes(app, worker)
    client = TestClient(app)
    result = client.get("/api/v1/observatory/series/cn_cpi?years=50")
    assert result.status_code == 200 and result.json()["coverage_short"]
    assert client.get("/api/v1/observatory/series/cn_cpi?years=7").status_code == 422
    assert client.get("/api/v1/observatory/series/cn_cpi?view=volatility").status_code == 422
    assert client.get("/api/v1/observatory/series/unknown").status_code == 404
    assert client.post("/api/v1/observatory/series/cn_cpi").status_code == 405
    csv = client.get("/api/v1/observatory/series/cn_cpi?years=0&output=csv")
    assert csv.status_code == 200 and "2026-07-31,,%" in csv.text and "2026-08-31,0.0,%" in csv.text
    assert client.get("/api/v1/observatory/news?days=7").status_code == 200
    assert client.get("/api/v1/observatory/news?days=9").status_code == 422


def test_service_completed_refresh_does_not_download_before_next_window(tmp_path, monkeypatch):
    from quantit.observatory import service
    atomic(tmp_path / "schedule.json", {"macro": NOW.isoformat(), "news": NOW.isoformat()})
    monkeypatch.setattr(service, "utcnow", lambda: NOW)
    monkeypatch.setattr(service, "download_dataset", lambda *a: pytest.fail("Unnecessary fetch"))
    worker = ObservatoryWorker(tmp_path)
    worker.refresh()
    assert read(tmp_path / "service.json")["state"] == "waiting"


def test_one_failed_news_source_retains_prior_articles(tmp_path, monkeypatch):
    from quantit.observatory import service
    atomic(tmp_path / "schedule.json", {"macro": NOW.isoformat()})
    atomic(tmp_path / "news.json", {"articles": [{"id": "old", "published_at": NOW.isoformat(), "title": "Saved"}], "sources": {}})
    monkeypatch.setattr(service, "utcnow", lambda: NOW)
    monkeypatch.setattr(service, "get_bytes", lambda *a: (_ for _ in ()).throw(ValueError("offline")))
    ObservatoryWorker(tmp_path).refresh()
    result = read(tmp_path / "news.json")
    assert result["articles"][0]["id"] == "old"
    assert len(result["sources"]) == 3 and all(s["error"] for s in result["sources"].values())


def test_local_ic_uses_mature_labels_and_isolates_missing_prediction(tmp_path, monkeypatch):
    from quantit.observatory.factors import local_ic
    dates = pd.bdate_range("2026-01-01", periods=80)
    rng = np.random.RandomState(3)
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, .01, (80, 8)), axis=0)),
                         index=dates, columns=[f"SH{i:06}" for i in range(8)])
    panel = pd.concat({"close": close, "volume": close * 100}, axis=1)
    panel.to_parquet(tmp_path / "panel.parquet")
    report = {"data_dir": str(tmp_path), "panel_sha256": hashlib.sha256((tmp_path / "panel.parquet").read_bytes()).hexdigest(),
              "data_asof": str(dates[-1].date()), "test_start": str(dates[60].date()),
              "test_last_signal": str(dates[-1].date()),
              "strategies": [{"id": "momentum_20", "horizon": 1}, {"id": "alpha158_lgbm_h5", "horizon": 5}]}
    (tmp_path / "report.json").write_text(json.dumps(report))
    monkeypatch.setenv("QUANTIT_OBSERVATORY_EXPERIMENT", str(tmp_path))
    result = local_ic()
    assert isinstance(result["local_alpha158_lgbm_h5"], FileNotFoundError)
    values, evidence = result["local_momentum_20"]
    assert values.index[-1] == dates[-2] and values.between(-1, 1).all()
    assert evidence["horizon_sessions"] == 1


def test_rejected_local_update_does_not_block_other_factors(tmp_path, monkeypatch):
    from quantit.observatory import service
    keys = ["local_alpha158_lgbm_h1", "local_momentum_20"]
    values = pd.Series([.1, .2, .3], index=pd.bdate_range("2026-10-12", periods=3))
    save_series(tmp_path, keys[0], values, {})
    atomic(tmp_path / "schedule.json", {"news": NOW.isoformat()})
    monkeypatch.setattr(service, "utcnow", lambda: NOW)
    monkeypatch.setattr(service, "SERIES", {k: SERIES[k] for k in keys})
    monkeypatch.setattr(service, "local_ic", lambda: {
        keys[0]: (values.iloc[:-1], {}), keys[1]: (values, {}),
    })
    ObservatoryWorker(tmp_path).refresh()
    assert "shrank" in summary(tmp_path, keys[0])["error"]
    assert summary(tmp_path, keys[1])["error"] is None
    assert summary(tmp_path, keys[1])["count"] == 3
