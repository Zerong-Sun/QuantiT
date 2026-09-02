"""Finnhub headlines → policy calendar proposal. Never a trade signal."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from quantit.data.news import NewsArticle
from quantit.research.params import research_dir

KEEP_TERMS = (
    "bis",
    "export control",
    "entity list",
    "tariff",
    "tariffs",
    "pboc",
    "csrc",
    "nsc",
    "ofac",
    "antitrust",
    "platform economy",
    "gaming license",
    "semiconductor control",
    "出口管制",
    "实体清单",
    "关税",
    "平台经济",
    "反垄断",
    "证监会",
    "央行",
)

DROP_TERMS = (
    "earnings beat",
    "earnings miss",
    "price target",
    "analyst",
    "stocks rally",
    "stocks plunge",
    "overbought",
    "oversold",
    "sentiment",
)


class BriefError(ValueError):
    """Invalid LLM proposal or brief input."""


def _blob(article: NewsArticle) -> str:
    return f"{article.headline} {article.summary}".lower()


def is_policy_event(article: NewsArticle) -> bool:
    text = _blob(article)
    keep = any(term in text for term in KEEP_TERMS)
    if not keep:
        return False
    drop = any(term in text for term in DROP_TERMS)
    if drop and not any(term in text for term in ("bis", "export control", "entity list", "出口管制", "实体清单")):
        return False
    return True


def filter_policy_articles(articles: list[NewsArticle]) -> list[NewsArticle]:
    return [a for a in articles if is_policy_event(a)]


def parse_llm_proposal(raw: str) -> dict[str, Any]:
    """Parse a regime patch. Rejects sentiment scores."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|yaml)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if "no_change" in text.lower() and "scores" not in text.lower():
        return {"decision": "no_change"}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BriefError(f"LLM output is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BriefError("LLM output must be a JSON object")
    lowered = {str(k).lower() for k in payload}
    if "sentiment" in lowered or "polarity" in lowered:
        raise BriefError("sentiment scores are not allowed; emit integer theme scores only")
    decision = str(payload.get("decision") or "apply")
    if decision == "no_change":
        return {"decision": "no_change"}
    scores = payload.get("scores")
    if not isinstance(scores, dict):
        raise BriefError("proposal must include integer theme scores")
    clean_scores = {str(k): int(v) for k, v in scores.items()}
    return {
        "decision": "apply",
        "name": str(payload.get("name") or "untitled_regime"),
        "start": str(payload.get("start") or date.today().isoformat()),
        "end": str(payload.get("end") or date.today().isoformat()),
        "scores": clean_scores,
        "notes": str(payload.get("notes") or ""),
        "evidence_urls": list(payload.get("evidence_urls") or []),
    }


def render_brief(
    articles: list[NewsArticle],
    intl: dict[str, float],
    regimes: list[dict[str, Any]],
    asof: str,
) -> str:
    lines = [
        f"# QuantiT policy brief ({asof})",
        "",
        "Do not trade headline sentiment. Output must be a policy-calendar patch",
        "(integer theme scores in [-2, 2]) or `no_change`. International factor stays",
        "on Yahoo macros; do not add a news beta on top of DXY.",
        "",
        "## International z-scores (price-based)",
    ]
    if intl:
        for key, value in intl.items():
            lines.append(f"- {key}: {value:.3f}")
    else:
        lines.append("- (unavailable)")
    lines.extend(["", "## Open policy regimes"])
    if regimes:
        for row in regimes:
            lines.append(f"- {row.get('name')}: {row.get('scores')}")
    else:
        lines.append("- (none covering asof)")
    lines.extend(["", "## Filtered Finnhub events"])
    if not articles:
        lines.append("- (no policy/geopolitics headlines in the lookback)")
    else:
        for article in articles:
            ts = article.datetime.strftime("%Y-%m-%d")
            lines.append(f"- [{ts}] {article.source}: {article.headline}")
            if article.url:
                lines.append(f"  {article.url}")
    lines.extend(
        [
            "",
            "## Requested output",
            "YAML/JSON with keys: decision, name, start, end, scores, notes, evidence_urls.",
            "Paste this brief into Cursor and ask for a calendar patch, or run `quantit brief --llm`.",
            "Do not merge into the live YAML without review. The paper runner does not read proposals.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_brief(markdown: str, when: date | None = None) -> Path:
    day = (when or date.today()).isoformat()
    path = research_dir() / "briefs" / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def write_proposal(payload: dict[str, Any], when: date | None = None) -> Path:
    day = (when or date.today()).isoformat()
    path = research_dir() / "policy_proposals" / f"{day}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


LLM_SYSTEM = """You map policy/geopolitics events into QuantiT's HK theme calendar.
Themes: platforms, hardware, semis, ev. Scores are integers in [-2, 2].
Never output sentiment, polarity, or a buy/sell. If nothing is a regime change, return {"decision":"no_change"}.
If a headline is already reflected in DXY/yields/Nasdaq, say so in notes and prefer no_change.
JSON only.
"""


def call_llm(prompt: str, opener=urlopen) -> str:
    base = os.environ.get("QUANTIT_LLM_BASE_URL") or "https://api.openai.com/v1"
    key = os.environ.get("QUANTIT_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    model = os.environ.get("QUANTIT_LLM_MODEL") or "gpt-4o-mini"
    if not key:
        raise BriefError("QUANTIT_LLM_API_KEY is not set")
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": LLM_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")
    request = Request(
        f"{base.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "QuantiT/0.1",
        },
    )
    try:
        with opener(request, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        raise BriefError(f"LLM request failed: {exc.reason}") from exc
    try:
        return str(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise BriefError("Unexpected LLM payload") from exc


def gather_articles(lookback_days: int = 7, extra_symbols: tuple[str, ...] = ()) -> list[NewsArticle]:
    from quantit.data.news import NewsClient

    client = NewsClient()
    articles = list(client.poll(None, lookback_days=lookback_days))
    for symbol in extra_symbols:
        try:
            articles.extend(client.poll(symbol, lookback_days=lookback_days))
        except Exception:
            continue
    return articles


def current_intl() -> dict[str, float]:
    from datetime import timedelta

    import pandas as pd

    from quantit.data.loader import DataLoader
    from quantit.data.macro import MacroLoader
    from quantit.features.regime import international_score

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%d")
    macros = MacroLoader(DataLoader()).load(start, end, skip_missing=True)
    if macros.empty:
        return {}
    series = international_score(macros)
    out: dict[str, float] = {}
    if not series.empty and not pd.isna(series.iloc[-1]):
        out["intl"] = float(series.iloc[-1])
    last = macros.iloc[-1]
    for col in ("dxy", "us10y", "nasdaq", "cny"):
        if col in last.index and pd.notna(last[col]):
            out[col] = float(last[col])
    return out


def open_regimes(asof: date | None = None) -> list[dict[str, Any]]:
    from quantit.policy.calendar import PolicyCalendar

    cal = PolicyCalendar.load_default()
    day = asof or date.today()
    scores = cal.scores_at(day, asof=day)
    covering = [r for r in cal.regimes if r.covers(day)]
    return [{"name": r.name, "scores": r.scores, "notes": r.notes} for r in covering] or [
        {"name": "(clipped totals)", "scores": scores}
    ]


def build_brief_markdown(lookback_days: int = 7) -> tuple[str, list[NewsArticle]]:
    asof = date.today().isoformat()
    try:
        articles = filter_policy_articles(
            gather_articles(lookback_days, extra_symbols=("AAPL", "0700.HK"))
        )
    except Exception:
        articles = []
    try:
        intl = current_intl()
    except Exception:
        intl = {}
    regimes = open_regimes()
    return render_brief(articles, intl, regimes, asof), articles
