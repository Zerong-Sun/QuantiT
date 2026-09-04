"""Closeloop CLI: ingest / factor / validate / run / sidecar."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from closeloop.data.fixture import FixtureDataPlane
from closeloop.data.protocol import DataPlane, default_data_dir
from closeloop.factors.alpha101 import UnsupportedAlphaError, compute_spec, list_alphas
from closeloop.factors.preprocess import prepare_factor
from closeloop.factors.spec import FactorSpec
from closeloop.library import load_library, render_report, upsert_record, write_report_md
from closeloop.loop.feedback import append_trace
from closeloop.loop.hypothesis import next_hypothesis
from closeloop.loop.sidecar import (
    default_artifacts_dir,
    list_inbox,
    read_spec,
    write_report,
)
from closeloop.validate.adapter import get_clean_factor_and_forward_returns, prices_from_panel
from closeloop.validate.gates import GateReport, GateThresholds, evaluate


def _plane(data_dir: Path | None, use_fixture: bool) -> DataPlane:
    if use_fixture:
        return FixtureDataPlane()
    from closeloop.data.qlib_cn import QlibCnDataPlane

    return QlibCnDataPlane(data_dir=data_dir)


def evaluate_spec(
    plane: DataPlane,
    spec: FactorSpec,
    start: str,
    end: str,
    artifacts_dir: Path | None = None,
    *,
    preprocess: bool = True,
    universe: str = "csi300",
    thresholds: GateThresholds | None = None,
) -> GateReport:
    panel = plane.load_panel(start, end)
    factor = compute_spec(spec, panel) * spec.sign()
    if preprocess:
        factor = prepare_factor(factor)
    prices = prices_from_panel(panel)
    clean = get_clean_factor_and_forward_returns(factor, prices)
    report = evaluate(clean, thresholds)
    if artifacts_dir is not None:
        append_trace(artifacts_dir, spec, report)
        upsert_record(artifacts_dir, spec, report, start=start, end=end, universe=universe)
    return report


def run_loop(
    plane: DataPlane,
    rounds: int,
    start: str,
    end: str,
    artifacts_dir: Path,
) -> list[GateReport]:
    history: list[str] = []
    reports: list[GateReport] = []
    for _ in range(rounds):
        spec = next_hypothesis(history)
        history.append(spec.padded_id())
        try:
            report = evaluate_spec(plane, spec, start, end, artifacts_dir=artifacts_dir)
        except UnsupportedAlphaError as exc:
            report = GateReport(
                passed=False,
                ic_mean=float("nan"),
                ic_ir=float("nan"),
                quantile_spread=float("nan"),
                turnover=float("nan"),
                reasons=[str(exc)],
            )
            append_trace(artifacts_dir, spec, report)
        reports.append(report)
    return reports


def _cmd_ingest(args: argparse.Namespace) -> int:
    from closeloop.data.ingest import ingest

    dest = ingest(
        dest=args.data_dir,
        universe=args.universe,
        start=args.start,
        end=args.end,
        from_csv=Path(args.from_csv) if args.from_csv else None,
        limit=args.limit,
        add_cap=not args.no_cap,
        industry_map_path=Path(args.industry_map) if args.industry_map else None,
    )
    print(dest)
    return 0


def _cmd_factor(args: argparse.Namespace) -> int:
    plane = _plane(args.data_dir, args.fixture)
    spec = FactorSpec(name=f"alpha{str(args.id).zfill(3)}", alpha_id=str(args.id))
    panel = plane.load_panel(args.start, args.end)
    factor = compute_spec(spec, panel)
    print(json.dumps({"alpha_id": spec.padded_id(), "shape": list(factor.shape)}, ensure_ascii=False))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    plane = _plane(args.data_dir, args.fixture)
    spec = FactorSpec(name=f"alpha{str(args.id).zfill(3)}", alpha_id=str(args.id))
    report = evaluate_spec(plane, spec, args.start, args.end, artifacts_dir=args.artifacts)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


def _cmd_run(args: argparse.Namespace) -> int:
    plane = _plane(args.data_dir, args.fixture)
    reports = run_loop(plane, args.rounds, args.start, args.end, args.artifacts)
    payload = [r.to_dict() for r in reports]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_sidecar(args: argparse.Namespace) -> int:
    plane = _plane(args.data_dir, args.fixture)
    artifacts = args.artifacts
    paths = list_inbox(artifacts)
    if args.once and not paths:
        print("no inbox YAML")
        return 0
    n = 0
    for path in paths:
        spec = read_spec(path)
        try:
            report = evaluate_spec(plane, spec, args.start, args.end, artifacts_dir=artifacts)
        except UnsupportedAlphaError as exc:
            report = GateReport(
                passed=False,
                ic_mean=float("nan"),
                ic_ir=float("nan"),
                quantile_spread=float("nan"),
                turnover=float("nan"),
                reasons=[str(exc)],
            )
            append_trace(artifacts, spec, report)
        out = artifacts / "outbox" / (path.stem + ".json")
        write_report(out, spec, report)
        n += 1
        if args.once:
            break
    print(json.dumps({"processed": n}, ensure_ascii=False))
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    print(json.dumps(list_alphas(), ensure_ascii=False, indent=2))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    rows = load_library(args.artifacts)
    md = render_report(rows)
    write_report_md(args.artifacts)
    print(md)
    return 0


def _cmd_train(args: argparse.Namespace) -> int:
    from closeloop.model.dataset import build_dataset
    from closeloop.model.train import train_predict_ic

    plane = _plane(args.data_dir, args.fixture)
    panel = plane.load_panel(args.start, args.end)
    ids = tuple(x.strip().zfill(3) for x in str(args.ids).split(",") if x.strip())
    ds = build_dataset(panel, alpha_ids=ids, horizon=args.horizon)
    result = train_predict_ic(ds, train_frac=args.train_frac)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="closeloop", description="A-share Qlib + Alpha101 + Alphalens research loop")
    p.add_argument("--data-dir", type=Path, default=None, help="Qlib dump directory")
    p.add_argument("--artifacts", type=Path, default=default_artifacts_dir())
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default="2024-12-31")
    p.add_argument("--fixture", action="store_true", help="Use synthetic panel (tests / no dump)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ingest_p = sub.add_parser("ingest", help="Write Qlib-shaped CSI300 dump")
    ingest_p.add_argument("--universe", default="csi300")
    ingest_p.add_argument("--from-csv", default=None)
    ingest_p.add_argument("--limit", type=int, default=None, help="Max CSI300 members (network ingest)")
    ingest_p.add_argument("--no-cap", action="store_true", help="Do not attach close*volume cap proxy")
    ingest_p.add_argument(
        "--industry-map",
        default=None,
        help="CSV/TSV of instrument,industry (申万一级 id) written into the panel",
    )
    ingest_p.set_defaults(func=_cmd_ingest)

    fac = sub.add_parser("factor", help="Compute one Alpha101 factor")
    fac.add_argument("--id", required=True)
    fac.set_defaults(func=_cmd_factor)

    val = sub.add_parser("validate", help="Alphalens gates for one alpha")
    val.add_argument("--id", required=True)
    val.set_defaults(func=_cmd_validate)

    run_p = sub.add_parser("run", help="Homegrown research loop")
    run_p.add_argument("--rounds", type=int, default=5)
    run_p.set_defaults(func=_cmd_run)

    side = sub.add_parser("sidecar", help="Consume RD-Agent inbox YAML")
    side.add_argument("--once", action="store_true")
    side.set_defaults(func=_cmd_sidecar)

    sub.add_parser("list", help="List Alpha101 registry").set_defaults(func=_cmd_list)
    sub.add_parser("report", help="Print factor library IC table").set_defaults(func=_cmd_report)

    train_p = sub.add_parser("train", help="Walk-forward model on Alpha101 features")
    train_p.add_argument("--ids", default="006,012,041,101")
    train_p.add_argument("--horizon", type=int, default=1)
    train_p.add_argument("--train-frac", type=float, default=0.7)
    train_p.set_defaults(func=_cmd_train)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.data_dir is None:
        args.data_dir = default_data_dir()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
