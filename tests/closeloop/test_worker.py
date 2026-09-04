from __future__ import annotations

from closeloop.data.fixture import FixtureDataPlane
from closeloop.factors.spec import FactorSpec
from closeloop.loop.book import target_book_from_factor
from closeloop.loop.hypothesis import MutateOnFailPolicy, RotateAlphaPolicy
from closeloop.loop.worker import LoopWorker
from closeloop.validate.gates import GateReport


def test_rotate_skips_history():
    policy = RotateAlphaPolicy()
    first = policy.next([], None)
    second = policy.next([first.padded_id()], None)
    assert first.padded_id() != second.padded_id()


def test_mutate_on_fail_flips_sign():
    policy = MutateOnFailPolicy()
    fail = GateReport(False, 0.0, 0.0, 0.0, 0.0, ["fail"])
    spec = policy.next(["006"], fail)
    assert spec.padded_id() == "006"
    assert spec.sign() == -1.0


def test_target_book_equal_weights():
    plane = FixtureDataPlane(n_days=20, n_instruments=6)
    close = plane.load_panel("2020-01-01", "2021-12-31")["close"]
    book = target_book_from_factor(close, "006", n_long=3)
    assert book is not None
    assert abs(sum(book.weights.values()) - 1.0) < 1e-9
    assert len(book.weights) == 3


def test_worker_step_fixture_does_not_trade(tmp_path):
    worker = LoopWorker(artifacts_dir=tmp_path, force_fixture=True, interval_sec=0.01)
    status, target = worker.step()
    assert status.source == "fixture"
    assert target is None
    assert status.last_alpha is not None
    assert (tmp_path / "library").exists() or status.n_library >= 0


def test_worker_error_advances_history(tmp_path):
    class Boom(RotateAlphaPolicy):
        def next(self, history, last_report):
            if not history:
                return FactorSpec(name="bad", alpha_id="999")
            return FactorSpec(name="alpha006", alpha_id="006")

    worker = LoopWorker(artifacts_dir=tmp_path, force_fixture=True, policy=Boom(), interval_sec=0.01)
    first, _ = worker.step()
    assert first.last_error
    assert "999" in worker.history
    second, _ = worker.step()
    assert second.last_alpha == "006"


def test_sidecar_inbox_only_skips_rotation(tmp_path):
    worker = LoopWorker(artifacts_dir=tmp_path, force_fixture=True, interval_sec=0.01)
    status, target = worker.step(inbox_only=True)
    assert target is None
    assert status.last_alpha is None
    assert worker.history == []


def test_inbox_yaml_writes_outbox(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "probe.yaml").write_text("alpha_id: '006'\nname: alpha006\n", encoding="utf-8")
    worker = LoopWorker(artifacts_dir=tmp_path, force_fixture=True, interval_sec=0.01)
    status, _ = worker.step(inbox_only=True)
    assert status.last_alpha == "006"
    assert (tmp_path / "outbox" / "probe.json").is_file()


def test_calendars_without_parquet_cannot_trade(tmp_path):
    (tmp_path / "calendars").mkdir()
    (tmp_path / "calendars" / "day.txt").write_text("2020-01-02\n", encoding="utf-8")
    worker = LoopWorker(artifacts_dir=tmp_path / "art", data_dir=tmp_path, force_fixture=False)
    assert worker.source() == "qlib_dump"
    assert worker.can_trade() is False
    _, target = worker.step()
    assert target is None
