"""Long-only target weights from a factor's latest cross-section (Q5-style)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class TargetBook:
    weights: dict[str, float]
    alpha_id: str
    rationale: str

    def to_dict(self) -> dict:
        return {"weights": dict(self.weights), "alpha_id": self.alpha_id, "rationale": self.rationale}


def target_book_from_factor(
    factor: pd.DataFrame,
    alpha_id: str,
    *,
    n_long: int = 5,
) -> TargetBook | None:
    if factor is None or factor.empty:
        return None
    last = factor.iloc[-1].dropna()
    if last.empty:
        return None
    k = max(1, min(int(n_long), len(last)))
    top = last.nlargest(k)
    weight = 1.0 / float(len(top))
    weights = {str(name): weight for name in top.index}
    names = ", ".join(weights)
    return TargetBook(
        weights=weights,
        alpha_id=str(alpha_id).zfill(3),
        rationale=f"alpha {alpha_id} top-{k} equal weight: {names}",
    )
