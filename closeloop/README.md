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

### Complete strategy experiment (new)

The separate `closeloop.model.experiment` workflow trains **three independent
Alpha158 + LightGBM candidates** (1/5/10-session targets), plus 20/60-session
momentum rule controls. All five remain shadow research strategies. The existing
`closeloop train` command below retains its single-holdout behavior.

```bash
# Preserve the paper service's .venv; use the existing research .venv311.
.venv311/bin/python -m closeloop.model.experiment \
  --data-dir "$HOME/.quantit/closeloop/qlib_cn_2026-10-20" \
  --output "$HOME/.quantit/closeloop/experiments/alpha158-2026-10-20-v1" \
  --threads 2
```

The output directory must be new. A completed run publishes `latest.json` in
its parent directory. The default API reader uses
`~/.quantit/closeloop/experiments/latest.json`; `QUANTIT_EXPERIMENT_REPORT` can
override it. The read-only `/api/v1/closeloop/experiments` endpoint and the
Research page show the results. No model deserialization or order submission
occurs in the API.

Protocol:

- Calendar-only 60%/20%/20% train/validation/final holdout boundaries; 60-session
  feature warm-up. Raw Alpha158 features have no fitted full-sample scaler.
- Features become usable one global market session later. Missing stock rows
  stay missing; shifts never skip suspensions.
- Every model fit purges the prediction horizon plus a five-session embargo.
  Training targets are date-local percentile ranks of forward close returns.
- First select holdings (10/20), rebalance frequency (5/10) and two-sided
  turnover cap (40%/80%) on validation. Then compare two regularized tree
  configurations on validation using that portfolio configuration. The objective
  is validation net return minus half the maximum drawdown magnitude.
- Freeze parameters before three expanding-window test folds. Earlier test
  history may enter later training only after labels mature and the embargo
  expires. Test results never select hyperparameters. A separate latest model
  is trained after evaluation; its predictions are not used for past OOS metrics.
- Independent long-only portfolios charge 15 bps on buys and 20 bps on sells,
  including assumed slippage/commission/tax; double-cost sensitivity is reported.
  Positions drift with returns, cash funds fees, initial entry is charged, and
  turnover includes both buys and sells. Signals from t−1 execute at t close;
  t→t+1 returns accrue after that execution. Missing held marks are explicitly
  flagged, and missing prices, zero volume and extreme daily moves block fills.
- Comparison is a monthly equal-weight reference on the **same fixed universe**,
  not an official CSI300 index. Report daily cross-sectional Rank IC, compounded
  net return, drawdown, Sharpe and three-fold stability.
- Frozen statistical gates: ≥126 OOS sessions; positive net return, positive
  Rank IC, outperform reference, maximum drawdown ≤20%, Sharpe ≥0.5, ≥2/3
  profitable folds, no stale held marks and positive return under double costs.

Even a statistical pass remains **ineligible for automatic trading**: the current
dump lacks point-in-time membership and adjustment provenance, and the fractional
daily-close execution proxy does not model board lots, minimum commission or full
market execution. This is an explicit data/execution gate, not a claim that a
successful backtest is deployable.

Artifacts include a manifest with data/code SHA-256, package versions, calendar
boundaries and all trial configurations; lagged features; selected parameters;
fold/latest LightGBM text models; OOS predictions; daily curves and complete
JSON reports. Do not tune against a published final holdout and call it untouched.

Audit the completed run independently:

```bash
.venv311/bin/python -m closeloop.model.verify_experiment \
  "$HOME/.quantit/closeloop/experiments/alpha158-2026-10-20-v1"
```

This checks source/panel checksums, verifies Qlib OHLCV bins against the panel,
checks each fold's purge boundaries, replays all five curves from the saved OOS
predictions or fixed rules, and writes artifact checksums to `verification.json`.

The implementation reuses the official
[Qlib Alpha158 handler and LightGBM benchmark approach](https://github.com/microsoft/qlib/tree/main/examples/benchmarks/LightGBM).
Public configuration values are not pretrained weights or evidence of local
profitability. Labels, execution assumptions, splits and conservative parameters
are explicitly recorded for this project rather than claiming a reproduction of
the official benchmark scores.

### Legacy single-holdout command

`closeloop train` builds a date×asset table of prepared Alpha101 columns plus `t+horizon` return, fits on the first date fraction, and reports OOS predicted IC. The chronological holdout purges `horizon` sessions before the test set and never splits one date across train/test. This is a single holdout, not rolling walk-forward or a cost-adjusted portfolio return. Backend: LightGBM if installed, else sklearn linear, else numpy least squares.

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
- Additional fixed **embargo**: `TRAIN_EMBARGO_DAYS` / `apply_train_embargo` remains a separate hook. The shared trainer now purges the label horizon; it does not apply this additional fixed five-session gap.

### Refresh stale research data

`python -m closeloop.data.refresh --source OLD_DUMP --destination NEW_DUMP --end YYYY-MM-DD`
downloads the existing fixed research universe to a new versioned directory.
This does not refresh historical CSI300 membership or correct survivorship bias.
`refresh.json` records every symbol's coverage. At least 95% must reach the end
date before a staged panel is written, and all names must retain history.
Missing latest rows remain missing. Keep the old dump and select the new one
with `CLOSELOOP_DATA_DIR`; use a new `CLOSELOOP_ARTIFACTS` directory to avoid
mixing old factor evaluations with the new dataset.

The API bridge prevents trading from dumps older than seven calendar days,
and the broker rejects stale/future prices. Zero-volume CL targets are not bought.

This path does **not** change gate thresholds or auto-place US/HK/CN orders. Paper results stay on book `cl`; trading still requires a gate pass on `cl` only.

## Official RD-Agent (sidecar only)

Keep [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) in another process. Drop factor YAML into `$CLOSELOOP_ARTIFACTS/inbox` (default `closeloop/artifacts/inbox/`). The resident worker lists that folder each step and writes metrics to `outbox/`. Do not `import` the official package in this repo.
