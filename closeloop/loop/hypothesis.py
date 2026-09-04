"""Pluggable hypothesis policies. Default rotates Alpha101; mutate-on-fail is a hook."""

from __future__ import annotations

from abc import ABC, abstractmethod

from closeloop.factors.alpha101 import supported_ids
from closeloop.factors.spec import FactorSpec
from closeloop.validate.gates import GateReport

DEFAULT_ORDER: tuple[str, ...] = (
    "006",
    "001",
    "012",
    "041",
    "101",
    "003",
    "004",
    "013",
    "044",
    "042",
) + tuple(
    aid
    for aid in supported_ids()
    if aid not in {"006", "001", "012", "041", "101", "003", "004", "013", "044", "042"}
)


class HypothesisPolicy(ABC):
    @abstractmethod
    def next(self, history: list[str], last_report: GateReport | None) -> FactorSpec:
        """Pick the next factor. ``history`` is padded alpha ids already tried this run."""


class RotateAlphaPolicy(HypothesisPolicy):
    def __init__(self, order: tuple[str, ...] | None = None) -> None:
        self.order = order or DEFAULT_ORDER

    def next(self, history: list[str], last_report: GateReport | None) -> FactorSpec:
        tried = set(history or [])
        for aid in self.order:
            if aid not in tried:
                return FactorSpec(name=f"alpha{aid}", alpha_id=aid)
        aid = self.order[len(history or []) % len(self.order)]
        return FactorSpec(name=f"alpha{aid}", alpha_id=aid)


class MutateOnFailPolicy(RotateAlphaPolicy):
    """If the last gate failed, retry the same alpha with flipped sign (LLM hook later)."""

    def next(self, history: list[str], last_report: GateReport | None) -> FactorSpec:
        if last_report is not None and not last_report.passed and history:
            last_id = history[-1]
            flipped = history.count(last_id) == 1
            if flipped:
                return FactorSpec(name=f"alpha{last_id}", alpha_id=last_id, params={"sign": -1.0})
        return super().next(history, last_report)


def next_hypothesis(history: list[str] | None = None, order: tuple[str, ...] | None = None) -> FactorSpec:
    return RotateAlphaPolicy(order).next(history or [], None)
