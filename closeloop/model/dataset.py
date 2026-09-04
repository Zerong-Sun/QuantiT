"""Feature matrix: Alpha101 columns + forward return label."""

from __future__ import annotations

import pandas as pd

from closeloop.data.protocol import field_frame
from closeloop.factors.alpha101 import compute_alpha
from closeloop.factors.ops import factor_stack
from closeloop.factors.preprocess import prepare_factor


def build_dataset(
    panel: pd.DataFrame,
    alpha_ids: tuple[str, ...],
    horizon: int = 1,
) -> pd.DataFrame:
    close = field_frame(panel, "close")
    label = factor_stack(close.shift(-horizon) / close - 1.0)
    label.name = "label"
    pieces = [label]
    for aid in alpha_ids:
        raw = compute_alpha(aid, panel)
        prepared = prepare_factor(raw)
        col = factor_stack(prepared)
        col.name = str(aid).zfill(3)
        pieces.append(col)
    return pd.concat(pieces, axis=1)
