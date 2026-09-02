"""Policy regime calendar (structured dates and theme scores, not news)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from quantit.markets.hk import THEME_NAMES


def _as_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass(frozen=True)
class PolicyRegime:
    """A dated policy regime with integer theme scores."""

    name: str
    start: date
    end: date
    scores: dict[str, int]
    notes: str = ""

    def covers(self, when: date) -> bool:
        return self.start <= when <= self.end


class PolicyCalendar:
    """Load and query overlapping policy regimes."""

    def __init__(
        self,
        regimes: list[PolicyRegime],
        themes: tuple[str, ...] = THEME_NAMES,
        clip: tuple[int, int] = (-2, 2),
    ) -> None:
        self.regimes = regimes
        self.themes = themes
        self.clip = clip

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> PolicyCalendar:
        themes = tuple(payload.get("themes") or THEME_NAMES)
        regimes: list[PolicyRegime] = []
        for raw in payload.get("regimes") or []:
            scores = {str(k): int(v) for k, v in (raw.get("scores") or {}).items()}
            regimes.append(
                PolicyRegime(
                    name=str(raw["name"]),
                    start=_as_date(raw["start"]),
                    end=_as_date(raw["end"]),
                    scores=scores,
                    notes=str(raw.get("notes") or ""),
                )
            )
        return cls(regimes=regimes, themes=themes)

    @classmethod
    def from_path(cls, path: str | Path) -> PolicyCalendar:
        text = Path(path).read_text(encoding="utf-8")
        payload = yaml.safe_load(text) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"Policy calendar YAML must be a mapping: {path}")
        return cls.from_mapping(payload)

    @classmethod
    def from_yaml(cls, text: str) -> PolicyCalendar:
        payload = yaml.safe_load(text) or {}
        if not isinstance(payload, dict):
            raise ValueError("Policy calendar YAML must be a mapping")
        return cls.from_mapping(payload)

    @classmethod
    def load_default(cls) -> PolicyCalendar:
        from importlib.resources import as_file, files

        ref = files("quantit.policy.data").joinpath("hstech_regimes.yaml")
        with as_file(ref) as path:
            return cls.from_path(path)

    @classmethod
    def load_cn(cls) -> PolicyCalendar:
        from importlib.resources import as_file, files

        ref = files("quantit.policy.data").joinpath("cn_etf_regimes.yaml")
        with as_file(ref) as path:
            return cls.from_path(path)

    def scores_at(self, when: str | date | datetime, asof: str | date | datetime | None = None) -> dict[str, int]:
        """Sum overlapping regime scores and clip to ``self.clip``.

        Dates strictly after ``asof`` (default: today) get zeros so the calendar
        does not project an open regime into the future.
        """
        day = _as_date(when)
        cap = _as_date(asof) if asof is not None else date.today()
        lo, hi = self.clip
        zeros = {theme: 0 for theme in self.themes}
        if day > cap:
            return zeros
        totals = dict(zeros)
        for regime in self.regimes:
            if not regime.covers(day):
                continue
            for theme, score in regime.scores.items():
                if theme in totals:
                    totals[theme] += score
        return {theme: max(lo, min(hi, val)) for theme, val in totals.items()}

    def series(self, dates, asof: str | date | datetime | None = None) -> "pd.DataFrame":
        """Build a DataFrame of clipped policy scores indexed by ``dates``."""
        import pandas as pd

        idx = pd.DatetimeIndex(dates)
        rows = [self.scores_at(ts.to_pydatetime(), asof=asof) for ts in idx]
        return pd.DataFrame(rows, index=idx)
