"""Audit saved input provenance and replay published strategy curves."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from closeloop.model.experiment import atomic_json, file_hash
from closeloop.model.portfolio import PortfolioConfig, simulate


def verify(output: Path) -> dict:
    report = json.loads((output / "report.json").read_text())
    data_dir = Path(report["data_dir"])
    if file_hash(data_dir / "panel.parquet") != report["panel_sha256"]:
        raise ValueError("Panel checksum changed")
    for filename, expected in report["source_hashes"].items():
        if Path(filename).name != filename or file_hash(Path(__file__).with_name(filename)) != expected:
            raise ValueError(f"Source checksum changed: {filename}")
    panel = pd.read_parquet(data_dir / "panel.parquet")
    calendar = pd.DatetimeIndex(panel.index)
    bins = 0
    for instrument in panel["close"].columns:
        for field in ("open", "high", "low", "close", "volume", "vwap"):
            values = np.fromfile(data_dir / "features" / instrument / f"{field}.day.bin", dtype="<f4")
            if len(values) != len(calendar) + 1 or values[0] != 0:
                raise ValueError(f"Unexpected qlib bin calendar for {instrument}/{field}")
            np.testing.assert_allclose(values[1:], panel[(field, instrument)].to_numpy(dtype=np.float32),
                                       rtol=0, atol=0, equal_nan=True)
            bins += 1
    checks = []
    for result in report["strategies"]:
        name = result["id"]
        if Path(name).name != name:
            raise ValueError("Invalid strategy identifier")
        for fold in result["training_folds"]:
            train_end = calendar.get_loc(pd.Timestamp(fold["train"]["end"]))
            test_start = calendar.get_loc(pd.Timestamp(fold["test_start"]))
            if train_end + fold["purge"] + fold["embargo"] >= test_start:
                raise ValueError(f"Label leakage in {name}")
        if name.startswith("alpha158"):
            predictions = pd.read_parquet(output / f"{name}-predictions.parquet")["prediction"]
            if predictions.index.has_duplicates:
                raise ValueError("Duplicate OOS predictions")
            scores = predictions.unstack("instrument")
            selection = json.loads((output / f"{name}-selection.json").read_text())
            if selection["config"] != result["portfolio"] or selection["model"] != result["model"]:
                raise ValueError("Selected parameters differ from evaluated parameters")
        else:
            lookback = int(name.rsplit("_", 1)[1])
            scores = (panel["close"] / panel["close"].shift(lookback) - 1).shift(1)
            scores = scores.where(panel["volume"].shift(1) > 0)
        curve = simulate(scores, panel["close"], panel["volume"], PortfolioConfig(**result["portfolio"]),
                         start=pd.Timestamp(report["test_start"]), end=pd.Timestamp(report["test_last_signal"]))
        saved = pd.read_csv(output / f"{name}-curve.csv", index_col="date", parse_dates=["date"])
        pd.testing.assert_frame_equal(curve, saved, check_freq=False, atol=1e-12, rtol=1e-12)
        compounded = float(np.prod(1 + saved.net_return) - 1)
        if not np.isclose(compounded, result["test"]["net_return"], atol=1e-12):
            raise ValueError("Reported cumulative return differs from saved curve")
        checks.append({"id": name, "replay_matches": True, "purge_verified": True})
    audit = {"passed": True, "qlib_bins_match_panel": bins, "strategies": checks,
             "artifact_sha256": {p.name: file_hash(p) for p in sorted(output.iterdir())
                                 if p.is_file() and p.name not in {"verification.json", "input-audit.json"}}}
    atomic_json(output / "verification.json", audit)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = verify(args.output.expanduser())
    print(json.dumps({k: v for k, v in result.items() if k != "artifact_sha256"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
