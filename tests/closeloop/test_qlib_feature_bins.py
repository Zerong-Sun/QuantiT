"""qlib FileFeatureStorage bins must start with a calendar start_index header."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from closeloop.data.ingest import write_qlib_layout
from closeloop.data.protocol import field_frame, panel_from_fields


def _read_qlib_bin(path: Path, start_index: int, end_index: int) -> np.ndarray:
    """Same layout as qlib.utils.read_bin: first float32 LE value is start_index."""
    with Path(path).open("rb") as handle:
        ref_start_index = int(np.frombuffer(handle.read(4), dtype="<f")[0])
        si = max(ref_start_index, start_index)
        if si > end_index:
            return np.array([], dtype=np.float32)
        handle.seek(4 * (si - ref_start_index) + 4)
        count = end_index - si + 1
        return np.frombuffer(handle.read(4 * count), dtype="<f")


def test_write_qlib_layout_bins_include_start_index_header(tmp_path):
    dates = pd.bdate_range("2020-01-02", periods=4)
    idx = pd.DatetimeIndex(dates, name="datetime")
    close = pd.DataFrame({"SH600000": [9.1, 9.2, 9.3, 9.4]}, index=idx)
    # Large volumes must not be mistaken for a calendar start_index.
    volume = pd.DataFrame(
        {"SH600000": [1_000_000.0, 1_100_000.0, 1_200_000.0, 1_300_000.0]},
        index=idx,
    )
    panel = panel_from_fields({"close": close, "volume": volume})
    dest = tmp_path / "qlib_cn"
    write_qlib_layout(panel, dest, universe="csi300")

    n_values = len(idx)
    for field, expected in (
        ("volume", volume["SH600000"].to_numpy(dtype=np.float32)),
        ("close", close["SH600000"].to_numpy(dtype=np.float32)),
    ):
        path = dest / "features" / "SH600000" / f"{field}.day.bin"
        raw = np.fromfile(path, dtype="<f")
        assert raw.shape == (1 + n_values,)
        assert raw[0] == 0.0
        np.testing.assert_array_equal(raw[1:], expected)
        got = _read_qlib_bin(path, start_index=0, end_index=n_values - 1)
        np.testing.assert_array_equal(got, expected)
        assert got.shape == (n_values,)

    parquet = pd.read_parquet(dest / "panel.parquet")
    pd.testing.assert_frame_equal(
        field_frame(parquet, "volume"),
        volume,
        check_freq=False,
        check_names=False,
    )


def test_write_qlib_feature_bin_round_trips_nonzero_start_index(tmp_path):
    from closeloop.data.ingest import write_qlib_feature_bin

    data = np.array([10.0, 11.0, 12.0], dtype=np.float64)
    start_index = 7
    path = tmp_path / "volume.day.bin"
    write_qlib_feature_bin(path, data, start_index=start_index)

    raw = np.fromfile(path, dtype="<f")
    assert raw.shape == (1 + len(data),)
    assert raw[0] == float(start_index)
    np.testing.assert_array_equal(raw[1:], data.astype("<f"))

    got = _read_qlib_bin(path, start_index=7, end_index=9)
    np.testing.assert_array_equal(got, data.astype("<f"))
    empty = _read_qlib_bin(path, start_index=0, end_index=6)
    assert empty.shape == (0,)
