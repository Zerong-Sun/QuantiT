"""Frozen pre-start model predictions for the separate raw-price paper history.

Writes only prediction files. Never imports the broker or places orders.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from closeloop.model.experiment import atomic_json, build_features, file_hash


def prepare(experiment: Path, data_dir: Path, destination: Path, start: str) -> dict:
    report = json.loads((experiment / "report.json").read_text())
    panel = pd.read_parquet(data_dir / "panel.parquet")
    calendar = pd.DatetimeIndex(panel.index)
    signal_start = pd.Timestamp(start)
    destination.mkdir(parents=True, exist_ok=True)
    source_features = experiment / "features.parquet"
    if file_hash(data_dir / "panel.parquet") == report["panel_sha256"]:
        features = pd.read_parquet(source_features)
    else:
        features = build_features(data_dir, panel)
    feature_dates = features.index.get_level_values("date")
    features = features.loc[feature_dates >= signal_start]
    features = features.loc[features.notna().any(axis=1)]
    contracts = {}
    for strategy in report["strategies"]:
        name = strategy["id"]
        selection = json.loads((experiment / f"{name}-selection.json").read_text())
        cfg = selection["config"]
        if name.startswith("alpha158"):
            # Never substitute the model fitted using October data into July.
            eligible = [f for f in strategy["training_folds"] if pd.Timestamp(f["test_start"]) <= signal_start]
            if not eligible:
                raise ValueError(f"No pre-start model for {name}")
            fold = max(eligible, key=lambda f: f["test_start"])
            end_i = calendar.get_indexer([pd.Timestamp(fold["train"]["end"])])[0]
            if end_i < 0 or end_i + strategy["horizon"] + fold["embargo"] >= calendar.searchsorted(signal_start):
                raise ValueError(f"Model labels are not mature before history starts: {name}")
            if pd.Timestamp(strategy["validation"]["end"]) >= signal_start:
                raise ValueError("Selection window overlaps history window")
            model_path = experiment / f"{name}-fold{fold['fold']}.txt"
            model = lgb.Booster(model_file=str(model_path))
            pred = pd.Series(model.predict(features[model.feature_name()]), index=features.index)
            scores = pred.unstack("instrument")
            model_info = {"file": str(model_path), "sha256": file_hash(model_path),
                          "train_end": fold["train"]["end"], "original_test_start": fold["test_start"],
                          "horizon": strategy["horizon"], "embargo": fold["embargo"]}
        else:
            lookback = int(name.rsplit("_", 1)[-1])
            scores = (panel["close"] / panel["close"].shift(lookback) - 1).shift(1)
            scores = scores.where(panel["volume"].shift(1) > 0).loc[start:]
            model_info = {"rule": name, "lookback": lookback}
        scores.to_parquet(destination / f"{name}.parquet")
        contracts[name] = {"name": strategy["name"], "portfolio": cfg, "model": model_info}
    result = {"start": start, "data_asof": str(calendar[-1].date()),
              "data_sha256": file_hash(data_dir / "panel.parquet"), "strategies": contracts,
              "files": {name: file_hash(destination / f"{name}.parquet") for name in contracts},
              "signal_convention": "feature bars through previous market session, execution at next open"}
    atomic_json(destination / "manifest.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--start", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.experiment, args.data_dir, args.destination, args.start), ensure_ascii=False))


if __name__ == "__main__":
    main()
