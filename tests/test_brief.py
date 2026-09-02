"""Policy headline filter and LLM proposal parser (no network)."""

from __future__ import annotations

import pytest

from quantit.data.news import NewsArticle
from datetime import datetime, timezone

from quantit.research.brief import (
    BriefError,
    filter_policy_articles,
    parse_llm_proposal,
    render_brief,
)


def _article(headline: str, summary: str = "") -> NewsArticle:
    return NewsArticle(
        symbol="general",
        headline=headline,
        summary=summary,
        source="test",
        url="https://example.com/1",
        datetime=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def test_keeps_export_control_drops_earnings() -> None:
    keep = _article("BIS expands semiconductor export controls to China")
    drop = _article("AAPL earnings beat; analyst raises price target as stocks rally")
    kept = filter_policy_articles([keep, drop])
    assert keep in kept
    assert drop not in kept


def test_parse_llm_rejects_sentiment_score() -> None:
    with pytest.raises(BriefError, match="sentiment"):
        parse_llm_proposal('{"decision": "apply", "sentiment": 0.8, "scores": {"semis": -2}}')


def test_parse_llm_regime_patch() -> None:
    raw = """
    {
      "decision": "apply",
      "name": "us_export_controls_2026",
      "start": "2026-09-01",
      "end": "2026-12-31",
      "scores": {"platforms": 0, "hardware": 0, "semis": -2, "ev": 0},
      "notes": "Entity List expansion; not priced in DXY.",
      "evidence_urls": ["https://example.com/1"]
    }
    """
    payload = parse_llm_proposal(raw)
    assert payload["scores"]["semis"] == -2
    assert "sentiment" not in payload


def test_render_brief_includes_macros_and_regimes() -> None:
    md = render_brief(
        articles=[_article("PBOC cuts reserve requirement ratio")],
        intl={"dxy": 0.4, "us10y": -0.2, "nasdaq": 0.1, "cny": 0.0},
        regimes=[{"name": "platform_easing", "scores": {"platforms": 1}}],
        asof="2026-09-02",
    )
    assert "PBOC" in md
    assert "platform_easing" in md
    assert "Do not trade headline sentiment" in md
