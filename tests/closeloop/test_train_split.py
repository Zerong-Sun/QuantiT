import numpy as np
import pandas as pd
import pytest

from closeloop.model.train import train_predict_ic


def dataset(days=20, horizon=3):
    index = pd.MultiIndex.from_product(
        [pd.bdate_range("2024-01-01", periods=days), ["a", "b", "c"]], names=["date", "instrument"]
    )
    frame = pd.DataFrame({"feature": np.arange(len(index)), "label": np.arange(len(index))*0.01}, index=index)
    frame.attrs["label_horizon"] = horizon
    return frame


def test_horizon_purge_and_whole_date_partition(monkeypatch):
    monkeypatch.setattr("closeloop.model.train._predict_numpy", lambda x, y, t: (t[:, 0], "fake"))
    frame = dataset()
    report = train_predict_ic(frame, 0.7)
    dates = frame.index.get_level_values("date").unique()
    assert report["train_end"] == str(dates[10].date())
    assert report["test_start"] == str(dates[14].date())
    assert report["n_train"] == 11*3
    assert report["n_test"] == 6*3
    assert report["purge_sessions"] == 3


@pytest.mark.parametrize("days", [1, 2, 3])
def test_small_sample_never_splits_same_day(days):
    with pytest.raises(ValueError, match="distinct dates"):
        train_predict_ic(dataset(days))


@pytest.mark.parametrize("frac", [0, 1, -0.1, float("nan")])
def test_invalid_split_fraction(frac):
    with pytest.raises(ValueError, match="train_frac"):
        train_predict_ic(dataset(), frac)
