from __future__ import annotations

import pandas as pd

from closeloop.data.ingest import ingest, load_industry_map
from closeloop.data.protocol import field_frame


def test_ingest_limit_from_csv_keeps_cap_if_present(tmp_path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    dates = pd.bdate_range("2020-01-02", periods=8)
    for inst in ("SH600000", "SZ000001"):
        pd.DataFrame(
            {
                "date": dates,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1_000_000,
            }
        ).to_csv(csv_dir / f"{inst}.csv", index=False)
    dest = tmp_path / "dump"
    ingest(dest=dest, from_csv=csv_dir, add_cap=True)
    panel = pd.read_parquet(dest / "panel.parquet")
    assert "cap" in panel.columns.get_level_values("field")
    cap = field_frame(panel, "cap")
    assert (cap > 0).all().all()
    assert (dest / "raw").is_dir()


def test_ingest_industry_map_file(tmp_path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    dates = pd.bdate_range("2020-01-02", periods=8)
    for inst in ("SH600000", "SZ000001"):
        pd.DataFrame(
            {
                "date": dates,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1_000_000,
            }
        ).to_csv(csv_dir / f"{inst}.csv", index=False)
    mapping = tmp_path / "sw1.csv"
    mapping.write_text("instrument,industry\nSH600000,1\nSZ000001,2\n", encoding="utf-8")
    loaded = load_industry_map(mapping)
    assert loaded == {"SH600000": 1.0, "SZ000001": 2.0}
    dest = tmp_path / "dump"
    ingest(dest=dest, from_csv=csv_dir, add_cap=False, industry_map_path=mapping)
    panel = pd.read_parquet(dest / "panel.parquet")
    industry = field_frame(panel, "industry")
    assert industry["SH600000"].iloc[0] == 1.0
    assert industry["SZ000001"].iloc[0] == 2.0
