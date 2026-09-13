"""Alpha158 dataset builder: train-path conventions without a live qlib dump."""

from __future__ import annotations

import pandas as pd
import pytest

from closeloop.data.fixture import FixtureDataPlane
from closeloop.data.protocol import field_frame
from closeloop.factors.ops import factor_stack
from closeloop.model.dataset import build_dataset
from closeloop.model.train import train_predict_ic


class _FakeAlpha158:
    """qlib-shaped handler: MultiIndex (datetime, instrument) × (feature, name)."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def fetch(self, col_set: str = "feature", **_kwargs) -> pd.DataFrame:
        if col_set == "label":
            return self._frame.iloc[:, :0]
        return self._frame


def _qlib_feature_frame(panel: pd.DataFrame, n_features: int = 4) -> pd.DataFrame:
    close = field_frame(panel, "close")
    dates = pd.DatetimeIndex(close.index, name="datetime")
    instruments = list(close.columns)
    idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    data = {f"K{i:03d}": (i + 1) * 0.01 for i in range(n_features)}
    # Extra name not on the parquet panel — builder must drop it when aligning.
    extra_idx = pd.MultiIndex.from_product(
        [dates, instruments + ["SZ999999"]], names=["datetime", "instrument"]
    )
    cols = pd.MultiIndex.from_product([["feature"], list(data)], names=[None, None])
    frame = pd.DataFrame(0.0, index=extra_idx, columns=cols)
    for i, name in enumerate(data):
        frame[("feature", name)] = float(i + 1)
    return frame


def test_build_alpha158_dataset_matches_train_path_conventions():
    from closeloop.model.alpha158 import build_alpha158_dataset

    plane = FixtureDataPlane(n_days=12, n_instruments=3, seed=3)
    panel = plane.load_panel("2020-01-01", "2021-12-31")
    handler = _FakeAlpha158(_qlib_feature_frame(panel))
    ds = build_alpha158_dataset(
        "2020-01-01",
        "2021-12-31",
        handler=handler,
        panel=panel,
        horizon=1,
    )
    ref = build_dataset(panel, alpha_ids=("006",), horizon=1)

    assert isinstance(ds.index, pd.MultiIndex)
    assert list(ds.index.names) == ["date", "instrument"]
    assert "label" in ds.columns
    feature_cols = [c for c in ds.columns if c != "label"]
    assert feature_cols == ["K000", "K001", "K002", "K003"]
    assert "SZ999999" not in ds.index.get_level_values("instrument")
    assert set(ds.index.get_level_values("instrument")) <= set(panel["close"].columns)

    # Same forward-return label as Alpha101 train path (no backward / same-bar leak).
    expected = factor_stack(field_frame(panel, "close").shift(-1) / field_frame(panel, "close") - 1.0)
    expected.index.names = ["date", "instrument"]
    aligned = expected.reindex(ds.index)
    pd.testing.assert_series_equal(ds["label"], aligned, check_names=False)

    last_date = ds.index.get_level_values("date").max()
    assert ds.loc[last_date, "label"].isna().all()
    first_date = ds.index.get_level_values("date").min()
    assert ds.loc[first_date, "label"].notna().all()

    # Drop-in for the existing walk-forward helper (needs the `date` level).
    result = train_predict_ic(ds, train_frac=0.6)
    assert "pred_ic" in result
    assert result["features"] == feature_cols

    ref_dates = set(pd.DatetimeIndex(ref.index.get_level_values("date")))
    ds_dates = set(pd.DatetimeIndex(ds.index.get_level_values("date")))
    assert ds_dates <= ref_dates


def test_build_alpha158_without_handler_requires_pyqlib(monkeypatch):
    from closeloop.model import alpha158

    plane = FixtureDataPlane(n_days=6, n_instruments=2)
    panel = plane.load_panel("2020-01-01", "2021-12-31")

    def _boom(_start, _end, _universe, **_kwargs):
        raise AssertionError("handler factory should not run when import fails")

    monkeypatch.setattr(alpha158, "_import_qlib", lambda: (_ for _ in ()).throw(
        ImportError("No module named qlib")
    ))
    monkeypatch.setattr(alpha158, "_make_alpha158_handler", _boom)
    with pytest.raises(ImportError, match=r"pip install -e '\.\[closeloop\]'"):
        alpha158.build_alpha158_dataset("2020-01-01", "2020-06-01", panel=panel)


def test_cli_train_accepts_alpha158_features():
    from closeloop.loop.run import build_parser

    parser = build_parser()
    args = parser.parse_args(["train", "--features", "alpha158", "--horizon", "1"])
    assert args.features == "alpha158"
    args101 = parser.parse_args(["train", "--ids", "006,012"])
    assert args101.features == "alpha101"
