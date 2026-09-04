from __future__ import annotations

from closeloop.data.fixture import FixtureDataPlane
from closeloop.loop.run import main
from closeloop.model.dataset import build_dataset
from closeloop.model.train import train_predict_ic


def test_build_dataset_has_label_and_features():
    plane = FixtureDataPlane(n_days=80, n_instruments=8)
    panel = plane.load_panel("2020-01-01", "2021-12-31")
    ds = build_dataset(panel, alpha_ids=("006", "012", "041"), horizon=1)
    assert "label" in ds.columns
    assert "006" in ds.columns
    assert ds.dropna().shape[0] > 10


def test_train_predict_ic_finite():
    plane = FixtureDataPlane(n_days=80, n_instruments=8)
    panel = plane.load_panel("2020-01-01", "2021-12-31")
    ds = build_dataset(panel, alpha_ids=("006", "012", "101"), horizon=1)
    result = train_predict_ic(ds, train_frac=0.7)
    assert "pred_ic" in result
    assert result["n_train"] > 0
    assert result["n_test"] > 0


def test_cli_train_fixture():
    assert main(["--fixture", "train", "--ids", "006,012,041"]) == 0
