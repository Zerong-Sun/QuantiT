# Research baseline (2012–2024 walk-forward)

Numbers below are copied from local HTML under `~/.quantit/research/` (not in git). Yahoo revisions can move Sharpe by a few hundredths. Commands are the protocol; figures are a snapshot.

Paper desk (US/HK/CN) and Closeloop (`cl`) stay isolated. Do not mix Alpha101 into HK/CN ETF rotation. Do not promote Nasdaq contrast results onto the quality paper book.

## Protocol

```bash
# Quality pool = paper watchlists. Do not pass --promote until the promote gate prints PASS.
quantit research --strategy tsmom --start 2012-01-01 --end 2024-12-31
quantit research --strategy hk_quality_book --start 2012-01-01 --end 2024-12-31
quantit research --strategy cn_quality_book --start 2012-01-01 --end 2024-12-31

# Audit only (Nasdaq contrast). Never add --promote.
quantit research --strategy tsmom --symbols AAPL,MSFT,NVDA,SPY,QQQ \
  --start 2012-01-01 --end 2024-12-31
```

Folds: train 504 / test 126 / step 126.

Promote universe (must match the paper book):

- `tsmom` → `US_QUALITY` (same as `US_WATCHLIST`)
- `hk_quality_book` → `HK_QUALITY`
- `cn_quality_book` → `CN_QUALITY`

`theme_rotation`, `cn_etf_rotation`, and `us_book` cannot promote (`spec.promote=False`).

## Two gates

**Report gate** (`evaluate_gates`): OOS Sharpe > 0, max drawdown ≥ −25% or not worse than buy-and-hold, OOS trades ≥ 4. Beating buy-and-hold Sharpe is **not** required.

**Promote gate** (`evaluate_promote_gates`): report gate, plus OOS Sharpe ≥ buy-and-hold Sharpe **or** Calmar-like (Sharpe / |max DD|) advantage, plus at least two bear folds whose OOS drawdown is ≥ −25% or not worse than that fold’s buy-and-hold. `--promote` also requires the quality universe.

Live YAML (`~/.quantit/research/active_params.yaml`, 2026-09-03) was written under the **report** gate: `us_primary=tsmom`, `hk_primary=hk_quality_book`, `cn_primary=cn_quality_book`. Re-running `--promote` on the quality-pool research numbers below would **not** rewrite those files.

## Dataset snapshot

| Study | File | Report | Promote | OOS Sharpe | OOS DD | BH Sharpe | BH DD | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US TSMOM quality (live book) | `tsmom_us_quality_2012.html` | PASS | **FAIL** | 0.05 | −18.8% | 0.53 | −50.8% | Calmar-like 0.27 vs 1.04 |
| US TSMOM quality (frozen params audit) | `audit_tsmom_live_us_quality_2012.html` | PASS | **FAIL** | 0.17 | −18.8% | 0.53 | −50.8% | Still lags BH |
| US TSMOM Nasdaq (audit) | `tsmom_us_nasdaq_2012.html` | PASS | metrics PASS, **universe FAIL** | 0.74 | −16.4% | 1.09 | −53.8% | Growth beta; must not promote |
| US `us_book` quality | `us_book_us_quality_2012.html` | PASS | spec forbids | 0.32 | −50.2% | 0.53 | −50.8% | DD uses the BH escape hatch |
| HK quality book | `hk_quality_book_2012.html` | PASS | **FAIL** | 0.06 | −14.1% | 0.31 | −17.5% | Live book |
| HK quality frozen | `hk_quality_book_frozen_2012.html` | PASS | PASS (Calmar) | 0.28 | −15.4% | 0.31 | −17.5% | Not the live YAML |
| HK per-name TSMOM | `tsmom_hk_quality_2012.html` | **FAIL** | FAIL | −0.43 | −23.3% | 0.13 | −36.6% | Basket is the HK path, not per-name |
| HK theme rotation research | `theme_rotation_2012.html` | PASS | spec forbids | 0.55 | −28.9% | 0.39 | −46.6% | Stay research-only |
| HK theme live audit | `audit_theme_live_hk_2012.html` | **FAIL** | FAIL | 0.56 | −43.8% | 0.59 | −41.2% | DD worse than BH |
| CN quality book | `tsmom_cn_quality_2012.html` | PASS | **FAIL** | 0.27 | −21.3% | 0.65 | −46.6% | Live book |
| CN quality frozen audit | `audit_tsmom_live_cn_quality_2012.html` | PASS | PASS (Calmar) | 0.44 | −21.3% | 0.65 | −46.6% | Better DD than BH; still weaker Sharpe |
| CN industry ETF | `cn_etf_rotation_2012.html` | **FAIL** | FAIL | −0.04 | −40.3% | −0.09 | −36.4% | Not the live path |

Bear folds on the quality studies were numerous and within drawdown; promote failures here are Sharpe/Calmar, not missing bear windows.

## L2 fill gap (research ≠ paper)

Walk-forward uses `Backtester(fill_on="next_open")` with **config commission (10 bp) and slippage (5 bp)**. Paper fills the delayed last print ± venue slippage (`same_close` analog). `quantit.research.fills.compare_fill_models` matches that split and does **not** search a grid.

JNJ, live TSMOM params (`lookback=252`, `skip=21`, `target_vol=0.15`, `risk_off_scale=0.5`), 2022-01-01 … 2024-12-31, $100k; paper-style arm uses 5 bp slippage:

| Fill | Sharpe | Max DD | Trades |
| --- | --- | --- | --- |
| `next_open` + config costs (research / WF) | −1.65 | −27.2% | 49 |
| `same_close` + 5 bp (paper) | −1.70 | −28.2% | 49 |
| delta (paper − research) | **−0.06** | **−1.0 pp** | 0 |

Same-window paper-style fills were still worse. Do not promote from this table. An earlier comparison that zeroed research costs overstated the gap (−0.15 Sharpe).

## L3 Closeloop CSI300

`~/.quantit/closeloop/qlib_cn/panel.parquet` is **missing** (`DUMP_MISSING`). AkShare ingest is not assumed to work.

- Fixture panels must not be reported as CSI300 results (`LoopWorker.source()=="fixture"` ⇒ `can_trade=False`).
- In-repo `closeloop/artifacts/library/` has no CSI300 JSON in this tree; an older 101-run (only alpha 078 passing) is **not** reproduced here.
- When a dump exists: `closeloop --data-dir ~/.quantit/closeloop/qlib_cn run --rounds 101` then `report`. Passed factors go to `TargetBook` top-5 **only on `cl`**. US/HK/CN cash must not move. Pytest `test_csi300_library_replay_requires_dump` skips until the parquet appears.

## How to re-score promote without promoting

After a study HTML exists, compare report vs promote in stdout (`Report gate:` / `Promote gate:`). Leave `--promote` off unless both the promote gate and the quality universe pass.
