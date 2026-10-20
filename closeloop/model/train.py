"""Purged chronological holdout: train then out-of-sample predicted IC."""

from __future__ import annotations

from importlib import import_module

import numpy as np
import pandas as pd


def _predict_numpy(train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray) -> tuple[np.ndarray, str]:
    train_x = np.nan_to_num(train_x, nan=0.0)
    test_x = np.nan_to_num(test_x, nan=0.0)
    train_y = np.nan_to_num(train_y, nan=0.0)
    try:
        import lightgbm as lgb
    except ModuleNotFoundError as exc:
        if exc.name != "lightgbm":
            raise
    else:
        model = lgb.LGBMRegressor(n_estimators=80, learning_rate=0.05, verbosity=-1)
        model.fit(train_x, train_y)
        return model.predict(test_x), "lightgbm"
    try:
        import_module("sklearn")
    except ModuleNotFoundError as exc:
        if exc.name != "sklearn":
            raise
    else:
        from sklearn.linear_model import LinearRegression

        model = LinearRegression()
        model.fit(train_x, train_y)
        return model.predict(test_x), "sklearn"
    beta, *_ = np.linalg.lstsq(train_x, train_y, rcond=None)
    return test_x @ beta, "numpy"


def train_predict_ic(dataset: pd.DataFrame, train_frac: float = 0.7) -> dict:
    """Chronological holdout with horizon-sized label purge (not walk-forward)."""
    if not 0 < train_frac < 1:
        raise ValueError("train_frac must be between zero and one")
    horizon = int(dataset.attrs.get("label_horizon", 1))
    if horizon < 1:
        raise ValueError("label_horizon must be positive")
    frame = dataset.replace([np.inf, -np.inf], np.nan).dropna().sort_index()
    if frame.empty:
        return {"pred_ic": None, "n_train": 0, "n_test": 0, "backend": "none", "features": []}
    date_vals = pd.DatetimeIndex(frame.index.get_level_values("date"))
    uniq = date_vals.unique().sort_values()
    cut_i = int(len(uniq) * train_frac)
    if cut_i <= horizon or cut_i >= len(uniq):
        raise ValueError("Not enough distinct dates for a purged chronological split")
    train = frame[date_vals < uniq[cut_i - horizon]]
    test = frame[date_vals >= uniq[cut_i]]
    feature_cols = [c for c in frame.columns if c != "label"]
    pred, backend = _predict_numpy(
        train[feature_cols].to_numpy(),
        train["label"].to_numpy(),
        test[feature_cols].to_numpy(),
    )
    y = test["label"].to_numpy()
    if len(y) < 3 or float(np.std(pred)) == 0.0 or float(np.std(y)) == 0.0:
        ic = None
    else:
        ic = float(np.corrcoef(pred, y)[0, 1])
    return {
        "pred_ic": ic,
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "backend": backend,
        "features": feature_cols,
        "split": "chronological_holdout",
        "purge_sessions": horizon,
        "train_end": str(train.index.get_level_values("date").max().date()),
        "test_start": str(test.index.get_level_values("date").min().date()),
    }
