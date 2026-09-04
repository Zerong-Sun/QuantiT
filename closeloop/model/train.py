"""Walk-forward style single split: train then OOS predicted IC."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _predict_numpy(train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray) -> tuple[np.ndarray, str]:
    train_x = np.nan_to_num(train_x, nan=0.0)
    test_x = np.nan_to_num(test_x, nan=0.0)
    train_y = np.nan_to_num(train_y, nan=0.0)
    try:
        import lightgbm as lgb

        model = lgb.LGBMRegressor(n_estimators=80, learning_rate=0.05, verbosity=-1)
        model.fit(train_x, train_y)
        return model.predict(test_x), "lightgbm"
    except Exception:
        pass
    try:
        from sklearn.linear_model import LinearRegression

        model = LinearRegression()
        model.fit(train_x, train_y)
        return model.predict(test_x), "sklearn"
    except Exception:
        beta, *_ = np.linalg.lstsq(train_x, train_y, rcond=None)
        return test_x @ beta, "numpy"


def train_predict_ic(dataset: pd.DataFrame, train_frac: float = 0.7) -> dict:
    frame = dataset.dropna()
    if frame.empty:
        return {"pred_ic": float("nan"), "n_train": 0, "n_test": 0, "backend": "none", "features": []}
    date_vals = pd.DatetimeIndex(frame.index.get_level_values("date"))
    uniq = date_vals.unique().sort_values()
    cut_i = max(1, min(len(uniq) - 2, int(len(uniq) * train_frac)))
    cut = uniq[cut_i]
    train = frame[date_vals <= cut]
    test = frame[date_vals > cut]
    if test.empty or train.empty:
        split = max(1, len(frame) * 3 // 4)
        train, test = frame.iloc[:split], frame.iloc[split:]
    feature_cols = [c for c in frame.columns if c != "label"]
    pred, backend = _predict_numpy(
        train[feature_cols].to_numpy(),
        train["label"].to_numpy(),
        test[feature_cols].to_numpy(),
    )
    y = test["label"].to_numpy()
    if len(y) < 3 or float(np.std(pred)) == 0.0 or float(np.std(y)) == 0.0:
        ic = float("nan")
    else:
        ic = float(np.corrcoef(pred, y)[0, 1])
    return {
        "pred_ic": ic,
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "backend": backend,
        "features": feature_cols,
    }
