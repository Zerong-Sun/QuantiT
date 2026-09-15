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
- Factors are never auto-promoted into the US/HK/CN paper runner (including `us_book`, `hk_theme`, and `cn_etf`).

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

Alpha158 research uses a **separate** `.venv311` (do not replace the existing `.venv`); official reproduce is under Training.

## CLI

```bash
# Local CSVs → dump (adds close*volume as cap proxy)
closeloop ingest --universe csi300 --from-csv /path/to/csv_dir

# Network CSI300 (resume via dest/raw/*.csv). Use --limit while iterating.
# Writes ~/.quantit/closeloop/qlib_cn/panel.parquet. Optional; skip a full 300-name pull unless you want live cl orders.
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

`closeloop train` builds a date×asset table of prepared Alpha101 columns plus `t+horizon` return, fits on the first date fraction, and reports OOS predicted IC. Backend: LightGBM if installed, else sklearn linear, else numpy least squares.

Optional **Alpha158 research feature matrix** — this is qlib's `Alpha158` handler wired to the local CSI300 dump, **not** a complete or promotable Alpha158 trading system. It does not replace Alpha101. Needs `pip install -e '.[closeloop]'` (in `.venv311`, below) and `~/.quantit/closeloop/qlib_cn` (calendars / instruments / `panel.parquet` / qlib bins). If pyqlib is missing the builder raises `ImportError`; it does **not** fall back to Alpha101 feature columns. The only shared pieces are the Closeloop `t+horizon` close-return **label** (not qlib `LABEL0`) and the existing `train_predict_ic` helper.

### Official reproduce (`.venv311`, research-only)

Create a **separate** `.venv311` with Homebrew `python@3.11`. Do **not** replace the existing `.venv`.

Verified on the maintainer machine (lock these numbers): Python **3.11.16**, qlib **0.9.7**, lightgbm **4.7.0**, sklearn **1.9.1**. `from closeloop.model.alpha158 import build_alpha158_dataset` imports.

```bash
# Homebrew python@3.11. Leave the existing .venv (paper / serve) untouched.
python3.11 -m venv .venv311
# if python3.11 is not on PATH:
# "$(brew --prefix python@3.11)/bin/python3.11" -m venv .venv311
source .venv311/bin/activate
python -V   # 3.11.16 on the maintainer lock
pip install -U pip
pip install -e '.[closeloop]'

python -c "import sys, qlib, lightgbm, sklearn; from closeloop.model.alpha158 import build_alpha158_dataset; print(sys.version.split()[0], qlib.__version__, lightgbm.__version__, sklearn.__version__)"
# expect: 3.11.16  0.9.7  4.7.0  1.9.1

# short example; needs ~/.quantit/closeloop/qlib_cn (not the fixture panel)
closeloop train --features alpha158
```

**Research-only.** `quantit serve` / the paper runner on port **8000** currently run under **Python 3.9** (system / CLT) and must keep using the existing `.venv` (or that 3.9 serve). Never activate `.venv311` for serve, and never bind `supervise.sh` / `quantit serve` to `.venv311`.

```python
from closeloop.model.alpha158 import build_alpha158_dataset
from closeloop.model.train import train_predict_ic

ds = build_alpha158_dataset("2020-01-01", "2024-12-31")  # date×instrument + label
train_predict_ic(ds)
```

Design hooks in `closeloop/model/alpha158.py` (documented, **not applied** in v1):

- Feature available day **day+1** (PIT / no same-day peek): `FEATURE_AVAILABLE_LAG_DAYS` / `apply_feature_available_lag`. Builder calls the hook with `lag=0`.
- Train/test **embargo**: `TRAIN_EMBARGO_DAYS` / `apply_train_embargo`. Not wired into `train_predict_ic` (contiguous date-fraction split, no gap).

This path does **not** change gate thresholds or auto-place US/HK/CN orders. Paper results stay on book `cl`; trading still requires a gate pass on `cl` only.

## Official RD-Agent (sidecar only)

Keep [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) in another process. Drop factor YAML into `$CLOSELOOP_ARTIFACTS/inbox` (default `closeloop/artifacts/inbox/`). The resident worker lists that folder each step and writes metrics to `outbox/`. Do not `import` the official package in this repo.
