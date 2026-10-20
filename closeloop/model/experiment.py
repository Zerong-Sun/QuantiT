"""Reproducible Alpha158 training and independent shadow strategy evaluation.

Run with the separate Python 3.11 research environment. No broker imports or
order-writing path. A new output directory is required for every experiment.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from closeloop.model.evaluation import daily_ic, forward_labels, gate_reasons, lag_features, training_dates
from closeloop.model.portfolio import PortfolioConfig, performance, simulate

VERSION = "alpha158-shadow-v1"
MODELS = {
    "compact": {"n_estimators": 160, "num_leaves": 15, "min_child_samples": 200, "reg_lambda": 20.0},
    "regularized": {"n_estimators": 240, "num_leaves": 31, "min_child_samples": 300, "reg_lambda": 50.0},
}
EMBARGO = 5
GRID = [PortfolioConfig(top_k=k, rebalance=r, turnover_limit=t)
        for k, r, t in itertools.product((10, 20), (5, 10), (0.4, 0.8))]
LIMITATIONS = [
    "固定股票池，非历史时点成分股，存在幸存者偏差",
    "使用当前复权历史，不是可审计的逐时点行情快照",
    "日线收盘成交代理、分数持仓、近似涨跌停和成本；未模拟整手、最低佣金及完整撮合",
    "研究结果不保证未来盈利；所有新增策略仅独立影子评估，不接入自动下单",
]


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fit_model(features: pd.DataFrame, labels: pd.Series, dates: pd.DatetimeIndex, params: dict, threads: int):
    import lightgbm as lgb

    mask = features.index.get_level_values("date").isin(dates)
    x = features.loc[mask]
    y = labels.reindex(x.index)
    valid = y.notna() & x.notna().any(axis=1)
    x, y = x.loc[valid], y.loc[valid]
    if len(x) < 100 or x.index.get_level_values("date").nunique() < 60:
        raise ValueError("Not enough training observations")
    # Date-local ranks remove market level; there is no fitted full-sample scaler.
    y = y.groupby(level="date").rank(pct=True) - 0.5
    model = lgb.LGBMRegressor(**params, learning_rate=0.03, colsample_bytree=0.8,
                             random_state=42, n_jobs=threads, verbosity=-1,
                             deterministic=True, force_col_wise=True)
    model.fit(x, y)
    return model, {"rows": len(x), "start": str(x.index.get_level_values("date").min().date()),
                   "end": str(x.index.get_level_values("date").max().date())}


def predict(model, features: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.Series:
    x = features.loc[features.index.get_level_values("date").isin(dates)]
    x = x.loc[x.notna().any(axis=1)]
    return pd.Series(model.predict(x), index=x.index, name="prediction")


def select_portfolio(scores: pd.DataFrame, close: pd.DataFrame, volume: pd.DataFrame,
                     start: pd.Timestamp, end: pd.Timestamp) -> tuple[PortfolioConfig, list[dict]]:
    trials = []
    for config in GRID:
        metrics = performance(simulate(scores, close, volume, config, start=start, end=end))
        # Frozen objective: validation net return minus half the drawdown magnitude.
        objective = metrics["net_return"] + 0.5 * metrics["max_drawdown"]
        trials.append({"config": asdict(config), "metrics": metrics, "objective": objective})
    best = max(trials, key=lambda row: row["objective"])
    return PortfolioConfig(**best["config"]), trials


def build_features(data_dir: Path, panel: pd.DataFrame) -> pd.DataFrame:
    import qlib
    from qlib.contrib.data.handler import Alpha158
    from closeloop.model.alpha158 import _as_date_instrument, _flatten_feature_columns

    qlib.init(provider_uri=str(data_dir), region="cn", kernels=2)
    handler = Alpha158(
        instruments=list(panel["close"].columns),
        start_time=str(panel.index.min().date()), end_time=str(panel.index.max().date()),
        infer_processors=[], learn_processors=[],
    )
    features = _as_date_instrument(_flatten_feature_columns(handler.fetch(col_set="feature")))
    if len(features.columns) != 158 or any(str(c).upper().startswith("LABEL") for c in features.columns):
        raise ValueError("Expected exactly 158 Alpha158 feature columns without labels")
    features = features.replace([np.inf, -np.inf], np.nan).astype("float32")
    lagged = lag_features(features, pd.DatetimeIndex(panel.index), lag=1)
    # Warm-up is excluded; each stock must have a valid preceding session.
    valid = panel["close"].shift(1).notna().stack(dropna=False)
    valid.index.names = ["date", "instrument"]
    lagged.loc[~valid.reindex(lagged.index).fillna(False)] = np.nan
    return lagged


def run_experiment(data_dir: Path, output: Path, *, threads: int = 2) -> dict:
    import lightgbm
    import qlib

    if threads < 1:
        raise ValueError("threads must be positive")
    if output.exists():
        raise FileExistsError("Use a new output directory; preserve previous experiments")
    panel_path = data_dir / "panel.parquet"
    panel = pd.read_parquet(panel_path).sort_index()
    calendar = pd.DatetimeIndex(panel.index)
    if calendar.has_duplicates or len(calendar) < 750:
        raise ValueError("At least 750 unique market sessions are required")
    close = panel["close"].astype(float)
    volume = panel["volume"].astype(float)
    if (close <= 0).any().any() or (volume < 0).any().any():
        raise ValueError("Invalid nonpositive prices or negative volume")
    # These boundaries depend only on the calendar, never on returns.
    valid_i, test_i = int(len(calendar) * 0.6), int(len(calendar) * 0.8)
    valid_start, test_start = calendar[valid_i], calendar[test_i]
    test_dates = calendar[test_i:-1]  # last mark has no next-day return
    folds = [pd.DatetimeIndex(d) for d in np.array_split(test_dates, 3)]
    output.mkdir(parents=True)
    manifest = {
        "version": VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_dir.resolve()), "panel_sha256": file_hash(panel_path),
        "data_start": str(calendar[0].date()), "data_asof": str(calendar[-1].date()),
        "sessions": len(calendar), "instruments": len(close.columns),
        "train_start": str(calendar[60].date()), "validation_start": str(valid_start.date()),
        "test_start": str(test_start.date()), "test_last_signal": str(test_dates[-1].date()),
        "feature_lag_sessions": 1, "label": "close[t+h]/close[t]-1; date-local percentile rank for fitting",
        "embargo_sessions": EMBARGO, "horizons": [1, 5, 10], "models": MODELS,
        "portfolio_grid": [asdict(c) for c in GRID], "seed": 42, "threads": threads,
        "versions": {"python": platform.python_version(), "qlib": qlib.__version__,
                     "lightgbm": lightgbm.__version__, "pandas": pd.__version__},
        "source_hashes": {p.name: file_hash(p) for p in (Path(__file__), Path(__file__).with_name("evaluation.py"),
                                                       Path(__file__).with_name("portfolio.py"))},
        "selection": "portfolio grid on compact model first, then model parameters; validation only",
        "limitations": LIMITATIONS, "automatic_trading": False,
    }
    atomic_json(output / "manifest.json", manifest)
    print("Building lagged Alpha158 features", flush=True)
    features = build_features(data_dir, panel)
    features.loc[features.index.get_level_values("date") < calendar[60]] = np.nan
    features.to_parquet(output / "features.parquet")
    results = []
    # Same-calendar equal-weight fixed-universe reference, same cost assumptions.
    reference_scores = close.notna().astype(float).shift(1)
    reference = simulate(reference_scores, close, volume,
                         PortfolioConfig(top_k=len(close.columns), rebalance=20, turnover_limit=2),
                         start=test_start, end=test_dates[-1])
    reference.to_csv(output / "benchmark.csv")
    benchmark = performance(reference)

    def finish(name, title, scores, config, horizon, selected, validation, fold_records, latest_scores):
        curve = simulate(scores, close, volume, config, start=test_start, end=test_dates[-1])
        curve.to_csv(output / f"{name}-curve.csv")
        metrics = performance(curve)
        fold_metrics = [performance(curve.loc[dates[0]:dates[-1]]) for dates in folds]
        labels = forward_labels(close, horizon)
        test_predictions = scores.reindex(test_dates).stack().rename_axis(["date", "instrument"])
        ic = daily_ic(test_predictions, labels)
        reasons = gate_reasons(metrics, benchmark, fold_metrics, ic)
        stress = performance(simulate(scores, close, volume, replace(config, buy_cost=config.buy_cost * 2,
                                     sell_cost=config.sell_cost * 2), start=test_start, end=test_dates[-1]))
        if stress["net_return"] <= 0:
            reasons.append("双倍交易成本下收益未大于零")
        latest_scores = latest_scores.replace([np.inf, -np.inf], np.nan).dropna().sort_values(ascending=False)
        result = {
            "id": name, "name": title, "mode": "shadow", "horizon": horizon,
            "model": selected, "portfolio": asdict(config), "validation": validation,
            "test": metrics, "ic": ic, "folds": fold_metrics, "training_folds": fold_records,
            "double_cost_test": stress, "statistical_gate_passed": not reasons,
            "gate_reasons": reasons, "promotion_eligible": False,
            "promotion_blockers": LIMITATIONS[:3], "automatic_trading": False,
            "latest_signal_date": str(calendar[-1].date()),
            "latest_ranking": [{"instrument": str(k), "score": float(v)}
                               for k, v in latest_scores.head(config.top_k).items()],
        }
        atomic_json(output / f"{name}.json", result)
        results.append(result)
        print(f"{name}: net={metrics['net_return']:.4f}, drawdown={metrics['max_drawdown']:.4f}, gate={not reasons}", flush=True)

    for horizon in (1, 5, 10):
        name = f"alpha158_lgbm_h{horizon}"
        labels = forward_labels(close, horizon).replace([np.inf, -np.inf], np.nan)
        train = training_dates(calendar, valid_start, horizon, EMBARGO)
        valid_end = calendar[test_i - horizon - EMBARGO - 1]
        valid_dates = calendar[(calendar >= valid_start) & (calendar <= valid_end)]
        print(f"{name}: selecting parameters on validation only", flush=True)
        model, _ = fit_model(features, labels, train, MODELS["compact"], threads)
        pred = predict(model, features, valid_dates)
        config, grid = select_portfolio(pred.unstack("instrument"), close, volume, valid_start, valid_end)
        selections = []
        for model_name, params in MODELS.items():
            if model_name != "compact":
                model, _ = fit_model(features, labels, train, params, threads)
                pred = predict(model, features, valid_dates)
            stats = performance(simulate(pred.unstack("instrument"), close, volume, config,
                                         start=valid_start, end=valid_end))
            selections.append({"model": model_name, "metrics": stats,
                               "objective": stats["net_return"] + 0.5 * stats["max_drawdown"]})
        chosen = max(selections, key=lambda x: x["objective"])["model"]
        validation = {"start": str(valid_start.date()), "end": str(valid_end.date()),
                      "portfolio_trials": grid, "model_trials": selections}
        # Persist the selection BEFORE opening the test set.
        atomic_json(output / f"{name}-selection.json",
                    {"model": chosen, "config": asdict(config), "validation": validation})
        predictions, records = [], []
        for i, dates in enumerate(folds):
            model, training = fit_model(features, labels, training_dates(calendar, dates[0], horizon, EMBARGO),
                                        MODELS[chosen], threads)
            predictions.append(predict(model, features, dates))
            records.append({"fold": i + 1, "train": training, "test_start": str(dates[0].date()),
                            "test_end": str(dates[-1].date()), "purge": horizon, "embargo": EMBARGO})
            model.booster_.save_model(str(output / f"{name}-fold{i + 1}.txt"))
        out_of_sample = pd.concat(predictions).sort_index()
        out_of_sample.to_frame().to_parquet(output / f"{name}-predictions.parquet")
        # Independent latest model: never used to calculate the preceding OOS results.
        latest_model, latest_training = fit_model(
            features, labels, training_dates(calendar, calendar[-1], horizon, EMBARGO), MODELS[chosen], threads)
        latest_model.booster_.save_model(str(output / f"{name}-latest.txt"))
        latest = predict(latest_model, features, calendar[-1:])
        latest.to_frame().to_parquet(output / f"{name}-latest.parquet")
        validation["latest_model_train"] = latest_training
        finish(name, f"Alpha158 · LightGBM {horizon} 日", out_of_sample.unstack("instrument"), config,
               horizon, chosen, validation, records, latest.droplevel("date"))

    for lookback in (20, 60):
        name = f"momentum_{lookback}"
        scores = (close / close.shift(lookback) - 1).shift(1)
        scores = scores.where(volume.shift(1) > 0)
        valid_end = calendar[test_i - 1 - EMBARGO - 1]
        config, trials = select_portfolio(scores, close, volume, valid_start, valid_end)
        selection = {"config": asdict(config), "validation": trials}
        atomic_json(output / f"{name}-selection.json", selection)
        finish(name, f"{lookback} 日动量对照", scores, config, 1, "rule",
               selection, [], scores.iloc[-1])

    report = {**manifest, "output_dir": str(output.resolve()), "benchmark": benchmark, "strategies": results,
              "completed_at": datetime.now(timezone.utc).isoformat()}
    atomic_json(output / "report.json", report)
    atomic_json(output.parent / "latest.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    result = run_experiment(args.data_dir.expanduser(), args.output.expanduser(), threads=args.threads)
    print(json.dumps({"output": result["output_dir"], "strategies": len(result["strategies"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
