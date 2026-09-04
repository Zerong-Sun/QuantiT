from __future__ import annotations

import pandas as pd
import pytest

from closeloop.data.fixture import FixtureDataPlane
from closeloop.data.ingest import ingest
from closeloop.data.protocol import field_frame
from closeloop.data.qlib_cn import QlibCnDataPlane


def test_fixture_panel_shape_and_fields():
    plane = FixtureDataPlane(n_days=40, n_instruments=6)
    panel = plane.load_panel("2020-01-01", "2020-12-31")
    assert panel.index.name == "datetime"
    assert list(panel.columns.names) == ["field", "instrument"]
    fields = set(panel.columns.get_level_values("field"))
    assert {"open", "high", "low", "close", "volume", "vwap"} <= fields
    close = field_frame(panel, "close")
    assert close.shape[1] == 6
    assert len(plane.instruments()) == 6
    assert len(plane.calendar()) == 40


def test_ingest_from_csv_roundtrip(tmp_path):
    plane = FixtureDataPlane(n_days=15, n_instruments=3, seed=1)
    panel = plane.load_panel("2020-01-01", "2021-01-01")
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    close = field_frame(panel, "close")
    for inst in close.columns:
        frame = pd.DataFrame(
            {
                "date": panel.index,
                "open": field_frame(panel, "open")[inst].to_numpy(),
                "high": field_frame(panel, "high")[inst].to_numpy(),
                "low": field_frame(panel, "low")[inst].to_numpy(),
                "close": close[inst].to_numpy(),
                "volume": field_frame(panel, "volume")[inst].to_numpy(),
                "vwap": field_frame(panel, "vwap")[inst].to_numpy(),
            }
        )
        frame.to_csv(csv_dir / f"{inst}.csv", index=False)
    dest = tmp_path / "qlib_cn"
    ingest(dest=dest, universe="csi300", from_csv=csv_dir)
    assert (dest / "calendars" / "day.txt").is_file()
    assert (dest / "instruments" / "csi300.txt").is_file()
    assert (dest / "panel.parquet").is_file()
    loaded = QlibCnDataPlane(data_dir=dest, prefer_qlib=False).load_panel("2020-01-01", "2021-01-01")
    assert loaded.shape[0] == panel.shape[0]
    pd.testing.assert_frame_equal(
        field_frame(loaded, "close").sort_index(axis=1),
        close.sort_index(axis=1),
        check_freq=False,
        rtol=1e-5,
        atol=1e-5,
    )


def test_qlib_features_preferred_when_calendars_exist(tmp_path, monkeypatch):
    from closeloop.data.protocol import panel_from_fields

    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    dates = pd.bdate_range("2020-01-02", periods=6)
    for inst in ("SH600000", "SZ000001"):
        pd.DataFrame(
            {
                "date": dates,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1_000,
                "vwap": 10.2,
            }
        ).to_csv(csv_dir / f"{inst}.csv", index=False)
    dest = tmp_path / "qlib_cn"
    ingest(dest=dest, universe="csi300", from_csv=csv_dir)
    fake_close = pd.DataFrame(
        {inst: 99.0 for inst in ("SH600000", "SZ000001")},
        index=pd.DatetimeIndex(dates, name="datetime"),
    )
    fake_panel = panel_from_fields(
        {
            "open": fake_close,
            "high": fake_close,
            "low": fake_close,
            "close": fake_close,
            "volume": fake_close,
            "vwap": fake_close,
        }
    )

    def _fake(self, start, end, fields):
        return fake_panel.loc[start:end]

    monkeypatch.setattr(QlibCnDataPlane, "_load_via_qlib", _fake)
    loaded = QlibCnDataPlane(data_dir=dest, prefer_qlib=True).load_panel("2020-01-02", "2020-12-31")
    assert (field_frame(loaded, "close") == 99.0).all().all()


@pytest.mark.network
def test_fetch_csi300_not_in_default_suite():
    pytest.skip("network ingest is manual")
