# Closeloop

Isolated research system: **Qlib data plane (A-share)** + **Alpha101 factors** + **Alphalens gates** + **factor library** + **LightGBM/linear train split** + **RD sidecar**.

This is **not** the paper desk, US Yahoo research path, Hang Seng TECH rotation, or A-share industry-ETF rotation. Those stay in `quantit/`.

## Boundaries

| Track | Data | Package |
|-------|------|---------|
| A-share CSI300 research | Qlib dump (`calendars` / `instruments` / panel) | `closeloop/` |
| US equities | Yahoo / existing cache | `quantit/` only |
| Paper trading / web | delayed quotes, SQLite | `quantit/` only |

Hard rules:

- `closeloop` does not import `quantit` (any submodule).
- `quantit.paper` / `strategy` / `markets` / `engine` do not import `closeloop`.
- The only exception is `quantit/api/closeloop_bridge.py`, which starts a resident `LoopWorker` and books the isolated paper account `cl`.
- Default universe is **CSI300 stocks**, not `510300` industry ETFs.
- Factors are never auto-promoted into the US/HK/CN paper runner.

## Layout

```
closeloop/
  data/       Qlib-shaped dump + load (A-share)
  factors/    ops, preprocess (winsorize/z-score), Alpha101 001–101
  validate/   Alphalens adapter + GateReport
  library.py  artifacts/library/*.json + REPORT.md
  model/      dataset + walk-forward train (LightGBM / sklearn / numpy)
  loop/       hypothesis → compute → gates → trace.jsonl
  artifacts/  inbox/ outbox/ library/
```

## Install

```bash
pip install -e ".[closeloop]"
```

Core tests run without `pyqlib` / AkShare (fixture panel). Those extras are for production ingest.

## CLI

```bash
# Local CSVs → dump (adds close*volume as cap proxy)
closeloop ingest --universe csi300 --from-csv /path/to/csv_dir

# Network CSI300 (resume via dest/raw/*.csv). Use --limit while iterating.
closeloop ingest --universe csi300 --start 2018-01-01 --end 2024-12-31 --limit 30

closeloop --fixture validate --id 006
closeloop --fixture run --rounds 5
closeloop --fixture report
closeloop --fixture train --ids 006,012,041,101
closeloop --fixture sidecar --once
```

Dump directory: `~/.quantit/closeloop/qlib_cn/` (not `~/.quantit/cache`).

Optional 申万一级 map: `closeloop ingest --from-csv ... --industry-map sw1.csv` (`instrument,industry` columns).

`quantit serve` starts `LoopWorker` next to `PaperRunner` (`QUANTIT_CLOSELOOP=0` disables it). The Research page at `/research` is the UI. Without a dump the worker uses the fixture panel and **does not** place `cl` orders.

## Factor library

Each `validate` / `run` writes `artifacts/library/{id}.json` (IC, IR, spread, turnover, sample window). `closeloop report` prints a markdown table and writes `library/REPORT.md`.

`cap` in the dump is **close × volume** (dollar-volume proxy), not official free-float market cap. `industry` is required for IndNeutralize alphas; the fixture assigns 3 synthetic groups. Pass a CSV via `ingest(..., industry_map_path=...)` or `--industry-map`.

## Training

`closeloop train` builds a date×asset table of prepared Alpha101 columns plus `t+horizon` return, fits on the first date fraction, and reports OOS predicted IC. Backend: LightGBM if installed, else sklearn linear, else numpy least squares. This is not a Qlib Alpha158 pipeline.

## Official RD-Agent (sidecar only)

Keep [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) in another process. Drop factor YAML into `$CLOSELOOP_ARTIFACTS/inbox` (default `closeloop/artifacts/inbox/`). The resident worker lists that folder each step and writes metrics to `outbox/`. Do not `import` the official package in this repo.
