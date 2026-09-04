from __future__ import annotations

import json

from closeloop.data.fixture import FixtureDataPlane
from closeloop.factors.spec import FactorSpec
from closeloop.library import load_library, render_report, upsert_record
from closeloop.loop.run import evaluate_spec, main, run_loop
from closeloop.validate.gates import GateReport


def test_upsert_and_report(tmp_path):
    spec = FactorSpec(name="alpha006", alpha_id="006")
    report = GateReport(True, 0.04, 0.9, 0.01, 0.3, ["ok"])
    path = upsert_record(tmp_path, spec, report, start="2020-01-01", end="2021-01-01", universe="csi300")
    assert path.is_file()
    rows = load_library(tmp_path)
    assert len(rows) == 1
    assert rows[0]["alpha_id"] == "006"
    md = render_report(rows)
    assert "alpha_id" in md or "006" in md


def test_evaluate_spec_writes_library(tmp_path):
    plane = FixtureDataPlane(n_days=80, n_instruments=8)
    spec = FactorSpec(name="alpha006", alpha_id="006")
    evaluate_spec(plane, spec, "2020-01-01", "2021-12-31", artifacts_dir=tmp_path)
    lib = tmp_path / "library"
    files = list(lib.glob("*.json"))
    assert files
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["alpha_id"] == "006"
    assert "ic_mean" in payload


def test_run_loop_fills_library(tmp_path):
    plane = FixtureDataPlane(n_days=60, n_instruments=6)
    run_loop(plane, rounds=2, start="2020-01-01", end="2021-12-31", artifacts_dir=tmp_path)
    assert len(list((tmp_path / "library").glob("*.json"))) == 2


def test_cli_report(tmp_path):
    plane = FixtureDataPlane(n_days=60, n_instruments=6)
    spec = FactorSpec(name="alpha012", alpha_id="012")
    evaluate_spec(plane, spec, "2020-01-01", "2021-12-31", artifacts_dir=tmp_path)
    assert main(["--fixture", "--artifacts", str(tmp_path), "report"]) == 0
