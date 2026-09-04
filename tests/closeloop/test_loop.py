from __future__ import annotations

import json

from closeloop.data.fixture import FixtureDataPlane
from closeloop.factors.spec import FactorSpec
from closeloop.loop.feedback import default_trace_path
from closeloop.loop.hypothesis import next_hypothesis
from closeloop.loop.run import evaluate_spec, main, run_loop
from closeloop.loop.sidecar import read_spec, write_report
from closeloop.validate.gates import GateReport


def test_hypothesis_skips_history():
    first = next_hypothesis([])
    second = next_hypothesis([first.padded_id()])
    assert first.padded_id() != second.padded_id()


def test_run_loop_writes_trace(tmp_path):
    plane = FixtureDataPlane(n_days=80, n_instruments=8)
    artifacts = tmp_path / "artifacts"
    reports = run_loop(plane, rounds=2, start="2020-01-01", end="2021-12-31", artifacts_dir=artifacts)
    assert len(reports) == 2
    trace = default_trace_path(artifacts)
    assert trace.is_file()
    lines = [json.loads(ln) for ln in trace.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    assert "alpha_id" in lines[0]
    assert "passed" in lines[0]


def test_evaluate_spec_alpha006(tmp_path):
    plane = FixtureDataPlane(n_days=80, n_instruments=8)
    spec = FactorSpec(name="alpha006", alpha_id="006")
    report = evaluate_spec(plane, spec, "2020-01-01", "2021-12-31", artifacts_dir=tmp_path)
    assert isinstance(report, GateReport)
    assert report.ic_mean == report.ic_mean or report.reasons


def test_sidecar_yaml_json_roundtrip(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    spec_path = inbox / "job.yaml"
    spec_path.write_text("name: alpha006\nalpha_id: '006'\nparams: {}\n", encoding="utf-8")
    spec = read_spec(spec_path)
    assert spec.padded_id() == "006"
    report = GateReport(True, 0.05, 1.2, 0.01, 0.4, ["all gates passed"])
    out = tmp_path / "outbox" / "job.json"
    write_report(out, spec, report)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["alpha_id"] == "006"


def test_cli_sidecar_once(tmp_path):
    inbox = tmp_path / "inbox"
    outbox = tmp_path / "outbox"
    inbox.mkdir()
    (inbox / "alpha012.yaml").write_text("name: a12\nalpha_id: '012'\nparams: {}\n", encoding="utf-8")
    code = main(
        [
            "--fixture",
            "--artifacts",
            str(tmp_path),
            "sidecar",
            "--once",
        ]
    )
    assert code == 0
    written = list(outbox.glob("*.json"))
    assert written
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["alpha_id"] == "012"


def test_cli_list_and_fixture_factor():
    assert main(["list"]) == 0
    assert main(["--fixture", "factor", "--id", "006"]) == 0
