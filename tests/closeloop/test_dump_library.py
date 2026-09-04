"""CSI300 dump library replay: skip without parquet; never treat fixture as CSI300."""

from __future__ import annotations

import pytest

from closeloop.data.protocol import default_data_dir
from closeloop.loop.worker import LoopWorker, parquet_exists


def test_fixture_source_is_not_csi300_dump(tmp_path) -> None:
    worker = LoopWorker(artifacts_dir=tmp_path, force_fixture=True)
    assert worker.source() == "fixture"
    assert worker.can_trade() is False


def test_csi300_library_replay_requires_dump() -> None:
    dest = default_data_dir()
    if not parquet_exists(dest):
        pytest.skip("DUMP_MISSING: no CSI300 panel.parquet under ~/.quantit/closeloop/qlib_cn")
    from closeloop.data.qlib_cn import QlibCnDataPlane
    from closeloop.data.protocol import field_frame

    plane = QlibCnDataPlane(data_dir=dest)
    panel = plane.load_panel("2020-01-01", "2020-03-31")
    close = field_frame(panel, "close")
    assert not close.empty
