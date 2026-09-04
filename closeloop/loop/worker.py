"""Background research worker. Does not import quantit."""

from __future__ import annotations

import os
import threading
import traceback
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from closeloop.data.fixture import FixtureDataPlane
from closeloop.data.protocol import DataPlane, default_data_dir
from closeloop.factors.alpha101 import UnsupportedAlphaError, compute_spec
from closeloop.factors.preprocess import prepare_factor
from closeloop.factors.spec import FactorSpec
from closeloop.library import load_library
from closeloop.loop.book import TargetBook, target_book_from_factor
from closeloop.loop.hypothesis import HypothesisPolicy, RotateAlphaPolicy
from closeloop.loop.run import evaluate_spec
from closeloop.loop.sidecar import default_artifacts_dir, list_inbox, outbox_dir, read_spec, write_report
from closeloop.validate.gates import GateReport, GateThresholds


def parquet_exists(data_dir: Path | None = None) -> bool:
    root = Path(data_dir) if data_dir is not None else default_data_dir()
    return (root / "panel.parquet").is_file()


def dump_exists(data_dir: Path | None = None) -> bool:
    root = Path(data_dir) if data_dir is not None else default_data_dir()
    return parquet_exists(root) or (root / "calendars" / "day.txt").is_file()


@dataclass
class WorkerStatus:
    running: bool = False
    source: str = "fixture"
    last_alpha: str | None = None
    last_tick: str | None = None
    last_error: str | None = None
    n_library: int = 0
    interval_sec: float = 45.0
    can_trade: bool = False
    ic_mean: float | None = None
    ic_ir: float | None = None
    passed: bool | None = None
    reasons: list[str] = field(default_factory=list)
    target: dict | None = None
    thresholds: dict | None = None

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "source": self.source,
            "last_alpha": self.last_alpha,
            "last_tick": self.last_tick,
            "last_error": self.last_error,
            "n_library": self.n_library,
            "interval_sec": self.interval_sec,
            "can_trade": self.can_trade,
            "ic_mean": self.ic_mean,
            "ic_ir": self.ic_ir,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "target": self.target,
            "thresholds": self.thresholds,
        }


class LoopWorker:
    def __init__(
        self,
        *,
        artifacts_dir: Path | None = None,
        data_dir: Path | None = None,
        interval_sec: float = 45.0,
        start: str = "2020-01-01",
        end: str = "2024-12-31",
        policy: HypothesisPolicy | None = None,
        thresholds: GateThresholds | None = None,
        force_fixture: bool | None = None,
    ) -> None:
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir is not None else default_artifacts_dir()
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.interval_sec = float(interval_sec)
        self.start = start
        self.end = end
        self.policy = policy or RotateAlphaPolicy()
        self.thresholds = thresholds or GateThresholds()
        if force_fixture is None:
            force_fixture = os.environ.get("CLOSELOOP_FIXTURE", "").strip() in {"1", "true", "yes"}
        self.force_fixture = bool(force_fixture)
        self.history: list[str] = []
        self._last_report: GateReport | None = None
        self._last_target: TargetBook | None = None
        self._status = WorkerStatus(interval_sec=self.interval_sec)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen_inbox: set[str] = set()

    def source(self) -> str:
        if self.force_fixture or not dump_exists(self.data_dir):
            return "fixture"
        return "qlib_dump"

    def can_trade(self) -> bool:
        return self.source() == "qlib_dump" and parquet_exists(self.data_dir)

    def _plane(self) -> DataPlane:
        if self.source() == "fixture":
            return FixtureDataPlane()
        from closeloop.data.qlib_cn import QlibCnDataPlane

        return QlibCnDataPlane(data_dir=self.data_dir)

    def _threshold_dict(self) -> dict:
        th = self.thresholds
        return {
            "ic_mean_abs": th.ic_mean_abs,
            "ic_ir": th.ic_ir,
            "require_quantile_spread_positive": th.require_quantile_spread_positive,
            "period": th.period,
        }

    def status(self) -> WorkerStatus:
        with self._lock:
            return replace(
                self._status,
                reasons=list(self._status.reasons),
                n_library=len(load_library(self.artifacts_dir)),
                source=self.source(),
                can_trade=self.can_trade(),
                running=self._status.running,
                interval_sec=self.interval_sec,
                thresholds=self._threshold_dict(),
            )

    def start_background(self) -> None:
        with self._lock:
            if self._status.running:
                return
            self._status.running = True
            self._stop.clear()
            previous = self._thread
            self._thread = threading.Thread(target=self._loop, name="closeloop-worker", daemon=True)
            thread = self._thread
        if previous is not None and previous.is_alive() and previous is not threading.current_thread():
            previous.join(timeout=min(2.0, self.interval_sec + 0.1))
        thread.start()

    def stop(self) -> None:
        with self._lock:
            self._status.running = False
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=min(2.0, self.interval_sec + 0.1))

    def _loop(self) -> None:
        self.step()
        while not self._stop.wait(self.interval_sec):
            if not self._status.running:
                return
            self.step()

    def step(self, *, inbox_only: bool = False) -> tuple[WorkerStatus, TargetBook | None]:
        target: TargetBook | None = None
        spec: FactorSpec | None = None
        inbox_path: Path | None = None
        try:
            picked = self._next_spec(inbox_only=inbox_only)
            if picked is None:
                return self.status(), None
            spec, inbox_path = picked
            plane = self._plane()
            report = evaluate_spec(
                plane,
                spec,
                self.start,
                self.end,
                artifacts_dir=self.artifacts_dir,
                thresholds=self.thresholds,
            )
            factor = compute_spec(spec, plane.load_panel(self.start, self.end))
            factor = prepare_factor(factor) * spec.sign()
            if report.passed:
                target = target_book_from_factor(factor, spec.padded_id())
            self.history.append(spec.padded_id())
            self._last_report = report
            self._last_target = target
            if inbox_path is not None:
                write_report(outbox_dir(self.artifacts_dir) / (inbox_path.stem + ".json"), spec, report)
            with self._lock:
                self._status.last_error = None
                self._status.last_alpha = spec.padded_id()
                self._status.ic_mean = report.ic_mean
                self._status.ic_ir = report.ic_ir
                self._status.passed = report.passed
                self._status.reasons = list(report.reasons)
                self._status.target = target.to_dict() if target else None
                self._status.last_tick = datetime.now(timezone.utc).isoformat()
                self._status.source = self.source()
                self._status.can_trade = self.can_trade()
                self._status.n_library = len(load_library(self.artifacts_dir))
                self._status.thresholds = self._threshold_dict()
        except UnsupportedAlphaError as exc:
            self._fail_spec(spec, inbox_path, str(exc))
        except Exception as exc:
            self._fail_spec(spec, inbox_path, f"{exc}\n{traceback.format_exc(limit=4)}")
        return self.status(), target if self.can_trade() else None

    def _fail_spec(self, spec: FactorSpec | None, inbox_path: Path | None, message: str) -> None:
        if spec is not None:
            self.history.append(spec.padded_id())
            report = GateReport(
                passed=False,
                ic_mean=float("nan"),
                ic_ir=float("nan"),
                quantile_spread=float("nan"),
                turnover=float("nan"),
                reasons=[message.split("\n", 1)[0]],
            )
            self._last_report = report
            if inbox_path is not None:
                write_report(outbox_dir(self.artifacts_dir) / (inbox_path.stem + ".json"), spec, report)
        self._record_error(message)

    def _record_error(self, message: str) -> None:
        with self._lock:
            self._status.last_error = message
            self._status.last_tick = datetime.now(timezone.utc).isoformat()

    def _next_spec(self, *, inbox_only: bool = False) -> tuple[FactorSpec, Path | None] | None:
        for path in list_inbox(self.artifacts_dir):
            key = str(path)
            if key in self._seen_inbox or path.name == "example.yaml":
                continue
            self._seen_inbox.add(key)
            return read_spec(path), path
        if inbox_only:
            return None
        return self.policy.next(self.history, self._last_report), None
