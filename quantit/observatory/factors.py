"""Historical IC from existing out-of-sample predictions, not refitted models."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from .sources import normalize


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_ic():
    folder = Path(os.environ.get("QUANTIT_OBSERVATORY_EXPERIMENT",
                                 str(Path.home() / ".quantit/closeloop/experiments/alpha158-2026-10-20-v1")))
    report_path = folder / "report.json"
    report = json.loads(report_path.read_text())
    panel_path = Path(report["data_dir"]) / "panel.parquet"
    panel_hash = checksum(panel_path)
    if panel_hash != report["panel_sha256"]:
        raise ValueError("Local research panel hash changed")
    panel = pd.read_parquet(panel_path)
    close = panel["close"]
    output = {}
    for strategy in report["strategies"]:
        name, horizon = strategy["id"], strategy["horizon"]
        try:
            path = folder / f"{name}-predictions.parquet"
            prediction_hash = None
            if name.startswith("momentum_"):
                lookback = int(name.rsplit("_", 1)[1])
                predicted = (close / close.shift(lookback) - 1).shift(1)
                predicted = predicted.where(panel["volume"].shift(1) > 0)
                predicted = predicted.loc[report["test_start"]:report["test_last_signal"]]
            else:
                predicted = pd.read_parquet(path)["prediction"].unstack("instrument")
                prediction_hash = checksum(path)
            label = close.shift(-horizon) / close - 1
            label = label.reindex(index=predicted.index, columns=predicted.columns)
            common = predicted.notna() & label.notna()
            a, b = predicted.where(common).rank(axis=1), label.where(common).rank(axis=1)
            correlations = a.corrwith(b, axis=1).where(common.sum(axis=1) >= 5)
            # Last incomplete labels are missing, not a fabricated zero IC.
            correlations = correlations.loc[:correlations.last_valid_index()]
            output[f"local_{name}"] = (normalize(correlations, "D"), {
                "experiment": folder.name, "prediction_sha256": prediction_hash,
                "panel_sha256": panel_hash, "report_sha256": checksum(report_path),
                "horizon_sessions": horizon, "source_asof": report["data_asof"],
                "method": "Daily cross-sectional Spearman correlation, minimum 5 common instruments; mature labels only.",
            })
        except Exception as exc:
            output[f"local_{name}"] = exc
    return output
