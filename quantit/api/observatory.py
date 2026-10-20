"""Cached observatory API; no upstream requests in GET handlers."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
import io
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from quantit.observatory.catalog import NEWS_SOURCES, SERIES
from quantit.observatory.store import read, series_view, summary, utcnow


def attach_observatory_routes(app: FastAPI, worker):
    root = worker.root

    @app.get("/api/v1/observatory")
    def catalog():
        state = read(root / "service.json", {"state": "unknown"})
        try:
            state["fresh"] = 0 <= (utcnow() - datetime.fromisoformat(state["heartbeat"])).total_seconds() < 600
        except (KeyError, ValueError, TypeError):
            state["fresh"] = False
        return {"series": [summary(root, key) for key in SERIES], "service": state,
                "revision_note": "使用当前修订后的历史数据。数据所属期不是首次公布日，不能直接当作历史交易时点可用信息。",
                "news_interval_minutes": 15, "macro_interval_hours": 6}

    @app.get("/api/v1/observatory/series/{key}")
    def observations(key: str, years: int = Query(5),
                     view: Literal["level", "change", "volatility"] = "level",
                     output: Literal["json", "csv"] = "json"):
        if key not in SERIES:
            raise HTTPException(404, "Unknown observatory series")
        if years not in {0, 5, 10, 50}:
            raise HTTPException(422, "years must be 0, 5, 10 or 50")
        try:
            payload = series_view(root, key, years, view)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if output == "json":
            return payload
        text = io.StringIO()
        writer = csv.writer(text)
        writer.writerow(["period_end", "value", "unit"])
        writer.writerows((p["date"], "" if p["value"] is None else p["value"], payload["unit"])
                        for p in payload["observations"])
        return Response("\ufeff" + text.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{key}-{view}-{years}y.csv"'})

    @app.get("/api/v1/observatory/news")
    def news(region: Literal["ALL", "US", "CN", "GLOBAL"] = "ALL",
             tag: str = Query("", max_length=30), q: str = Query("", max_length=100),
             days: int = Query(7)):
        if days not in {0, 7, 30}:
            raise HTTPException(422, "days must be 0, 7 or 30")
        data = read(root / "news.json", {"articles": [], "sources": {}})
        cutoff = (utcnow() - timedelta(days=days)).isoformat() if days else ""
        results = []
        for article in data["articles"]:
            if region != "ALL" and article["region"] != region:
                continue
            if tag and tag not in article["tags"]:
                continue
            if q and q.casefold() not in article["title"].casefold():
                continue
            if cutoff and (not article.get("published_at") or article["published_at"] < cutoff):
                continue
            results.append(article)
        sources = []
        for key, source in NEWS_SOURCES.items():
            status = data.get("sources", {}).get(key, {})
            try:
                stale = (utcnow() - datetime.fromisoformat(status["fetched_at"])).total_seconds() > 3600
            except (KeyError, ValueError, TypeError):
                stale = True
            sources.append({"id": key, **source, **status, "stale": stale})
        return {"articles": results[:300], "matched_count": len(results), "sources": sources,
                "truncated": len(results) > 300,
                "updated_at": data.get("updated_at"),
                "note": "公开 RSS 定时抓取，非实时快讯或完整历史档案。风险标签来自标题关键词，不代表已核实的风险判断。"}
