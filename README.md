# QuantiT

A research-oriented quantitative trading platform for US equities, Hong Kong long-horizon strategies, and onshore A-share industry ETFs, plus a paper trading terminal covering US, HK, and A-shares. US research path: technical factors and event-driven backtesting, with optional news polling (no live trading). HK path: Hang Seng TECH / Chinese internet theme rotation from supply-demand, policy regimes, and international macros. A-share path: industry ETF rotation (semis / NEV / healthcare / defense) from ETF demand versus CSI 300, an industrial-policy calendar, and the same macros. Paper terminal: delayed K-lines, simulated fills, and persisted orders.

## Current capabilities

- **Data**: Yahoo Finance OHLCV with Parquet caching (gap-aware); HK `.HK` names and macro series; A-share / ETF bars via local CSV (`materials/etf_history_clean.csv`) plus AkShare
- **Markets**: Pluggable `MarketAdapter` registry (`us`, `hk`, `cn`) — add a venue without changing API routes
- **Factors**: Technical indicators (SMA, EMA, RSI, MACD, Bollinger, ATR, momentum, volatility)
- **Strategies**: Time-series momentum with volatility targeting (US research default); MA/RSI `us_book` as a paper baseline; HK monthly theme rotation; CN industry ETF monthly rotation
- **Research**: Walk-forward grid search (`quantit research`); report gate vs stricter promote gate; only the paper quality universe can write `~/.quantit/research/active_params.yaml`. See `research/BASELINE.md`.
- **Backtest**: Bar-by-bar simulation; single-name signals fill on the next bar's open by default
- **Paper terminal**: Delayed quotes (polling), market orders, auto-runner for catalog strategies, **one cash account per strategy** sharing US/HK/CN venue adapters (US quality TSMOM + US MA/RSI, HK quality TSMOM + Hang Seng TECH rotation, CN quality TSMOM + industry ETFs, plus an isolated **CL ¥1m** CSI300 research book). A-share T+1 and board lots. Top-bar **Research** (`/research`) runs Closeloop (Alpha101 + gates) without mixing into any US/HK/CN paper book.
- **Analysis**: Performance metrics, Plotly charts, HTML reports
- **News / policy**: Finnhub REST polling for headlines. Headlines **do not** trade. `quantit brief` filters policy/geopolitics events into a markdown pack (plus Yahoo international macros). Optional `--llm` writes a YAML calendar proposal; it is **not** auto-merged and the paper runner does not read it.

ML and RL are not implemented yet. Quotes are delayed public-source data, not a live broker feed.

## Quick start

```bash
pip install -e ".[dev]"

# Run MA crossover backtest
python examples/ma_crossover.py

# Hang Seng TECH theme rotation (monthly, HK)
python examples/hk_tech_rotation.py

# Onshore industry ETF rotation (monthly, A-share)
python examples/cn_etf_rotation.py

# CLI backtest (MA crossover)
quantit backtest --symbol AAPL --start 2020-01-01 --end 2024-12-31

# Walk-forward research (default: US quality book, not Nasdaq). Report gate ≠ promote gate.
quantit research --strategy tsmom --start 2012-01-01 --end 2024-12-31
# Nasdaq contrast is audit-only — do not pass --promote.
quantit research --strategy tsmom --symbols AAPL,MSFT,NVDA,SPY,QQQ \
  --start 2012-01-01 --end 2024-12-31
quantit research --strategy hk_quality_book --start 2012-01-01 --end 2024-12-31
quantit research --strategy cn_quality_book --start 2012-01-01 --end 2024-12-31
```

### Paper trading terminal (US / HK / A-shares)

The UI is a web app. Do **not** open `web/index.html` in the browser as a file (it will be blank).

```bash
pip install -e ".[paper]"
cd web && npm install && npm run build && cd ..
quantit serve --host 127.0.0.1 --port 8000
```

Then open **http://127.0.0.1:8000/** (`quantit serve` opens it by default). Quotes refresh about every 15 seconds. Paper fills use the last delayed **close** plus venue slippage/commission (not research `next_open`; see `research/BASELINE.md` L2 / F2). A-shares require `akshare` (included in the `paper` extra).

Idle paper books are seeded at **USD 100,000** each for US quality TSMOM and US MA/RSI, **HKD 1,000,000** each for HK quality and Hang Seng TECH rotation (warrants overlay the theme book), and **CNY 1,000,000** each for CN quality and industry-ETF rotation. The runner ticks every desk book each session except MA/RSI `us_book`, which is off unless `QUANTIT_US_BOOK_AUTO=1` (or `true`/`yes`); an explicit `markets=us_book` tick (`POST /api/v1/runner/tick?market=us_book`) still runs it for manual testing (at most once per calendar day; turnover bands skip tiny size changes). YAML `us_primary` / `hk_primary` / `cn_primary` still record research `--promote` params and no longer hide the other books. Options overlay lives on `us_book`; warrants on `hk_theme`. Closeloop uses a separate **CL CNY 1,000,000** book (`market_id=cl`) that the paper runner never ticks. Open **http://127.0.0.1:8000/research** for the research loop. Set `QUANTIT_RUNNER=0` to pause the desk runner; `QUANTIT_CLOSELOOP=0` to pause Closeloop. Without a CSI300 dump (`closeloop ingest --universe csi300` → `~/.quantit/closeloop/qlib_cn/panel.parquet`) the worker uses a fixture panel and does not place `cl` orders.

Long-running `quantit serve` (for example under `~/.quantit/runners/supervise.sh`) can set `QUANTIT_LOG_FILE` to write rotating file logs (default 5 MB × 5 backups; override with `QUANTIT_LOG_MAX_BYTES` / `QUANTIT_LOG_BACKUPS`) while still logging to the console. Unset, local serve keeps uvicorn's default console-only logging. Out-of-repo supervise restarts on **exit**, not when a child is still alive but no longer LISTENs; `bash scripts/check_runners.sh` checks ports **8000** / **5173**. One-click restart and the HTML-as-JSON symptom (`API 返回了 HTML 而不是 JSON` / old `Unexpected token '<'`): [`knowledge_base/11_paper/runners.md`](knowledge_base/11_paper/runners.md).

If the paper UI says the API returned HTML instead of JSON, open **http://127.0.0.1:8000/** (do not open a stale static page or a Vite proxy whose backend is dead), hard-refresh, and restart `quantit serve`.

Review of whether those live rules are reasonable, tradable at this size, and what to expect next: [`knowledge_base/11_paper/strategy_review.md`](knowledge_base/11_paper/strategy_review.md).

For live reload during UI development, keep the API running and in another shell:

```bash
cd web
npm run dev
```

Then use http://localhost:5173 (Vite proxies `/api` to port 8000).

### News (Finnhub) and policy briefs

1. Register a free key at [finnhub.io/register](https://finnhub.io/register)
2. Copy `.env.example` to `.env` and set `FINNHUB_API_KEY` (`.env` is gitignored). You can also `export FINNHUB_API_KEY=...`.

```bash
quantit news --symbol AAPL
quantit news --symbol AAPL --watch --interval 30
```

Or run `python examples/news_feed.py`. Finnhub is **not** a trading signal. HK/CN international scores stay on Yahoo macros (DXY, US 10Y, Nasdaq, USDCNY). Policy scores stay on the YAML calendar.

To review policy/geopolitics headlines (export controls, tariffs, PBOC/CSRC, etc.) without sentiment trading:

```bash
quantit brief
```

That writes `~/.quantit/research/briefs/YYYY-MM-DD.md`. Open it in Cursor and ask for a policy-calendar patch (integer theme scores). Optional LLM:

```bash
export QUANTIT_LLM_API_KEY=...
export QUANTIT_LLM_MODEL=gpt-4o-mini   # optional
quantit brief --llm
```

`--llm` writes `~/.quantit/research/policy_proposals/` only. Merge into `quantit/policy/data/hstech_regimes.yaml` by hand. The paper runner never reads that folder.

## Project structure

```
quantit/          # Core library (markets, paper broker, FastAPI)
web/              # React paper terminal
examples/         # Example strategies
tests/            # Unit tests
knowledge_base/   # Theory notes (not a feature checklist)
```

Optional extras (not required for backtests):

```bash
pip install -e ".[ml]"       # torch, xgboost, sklearn, …
pip install -e ".[paper]"    # FastAPI server + AkShare A-share data
```

`[dashboard]` is an alias of `[paper]` (the Streamlit dashboard was never shipped).

## License

MIT
