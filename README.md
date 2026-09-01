# QuantiT

A research-oriented quantitative trading platform for US equities, Hong Kong long-horizon strategies, and a paper trading terminal covering US, HK, and A-shares. US research path: technical factors and event-driven backtesting, with optional news polling (no live trading). HK path: Hang Seng TECH / Chinese internet theme rotation from supply-demand, policy regimes, and international macros. Paper terminal: delayed K-lines, simulated fills, and persisted orders.

## Current capabilities

- **Data**: Yahoo Finance OHLCV with Parquet caching (gap-aware); HK `.HK` names and macro series; A-share bars via AkShare
- **Markets**: Pluggable `MarketAdapter` registry (`us`, `hk`, `cn`) — add a venue without changing API routes
- **Factors**: Technical indicators (SMA, EMA, RSI, MACD, Bollinger, ATR, momentum, volatility)
- **Strategies**: Moving-average crossover and RSI mean reversion (single symbol); HK monthly theme rotation (multi-asset)
- **Backtest**: Bar-by-bar simulation; single-name signals fill on the next bar's open by default
- **Paper terminal**: Delayed quotes (polling), market orders, three currency sub-accounts, A-share T+1 and board lots
- **Analysis**: Performance metrics, Plotly charts, HTML reports
- **News**: Finnhub REST polling for company and general market headlines (US research/testing only; not used by the HK regime path)

ML and RL are not implemented yet. Quotes are delayed public-source data, not a live broker feed.

## Quick start

```bash
pip install -e ".[dev]"

# Run MA crossover backtest
python examples/ma_crossover.py

# Hang Seng TECH theme rotation (monthly, HK)
python examples/hk_tech_rotation.py

# CLI backtest
quantit backtest --symbol AAPL --start 2020-01-01 --end 2024-12-31
```

### Paper trading terminal (US / HK / A-shares)

The UI is a web app. Do **not** open `web/index.html` in the browser as a file (it will be blank).

```bash
pip install -e ".[paper]"
cd web && npm install && npm run build && cd ..
quantit serve --host 127.0.0.1 --port 8000
```

Then open **http://127.0.0.1:8000/** (`quantit serve` opens it by default). Quotes refresh about every 15 seconds. Paper fills use the last delayed bar plus venue slippage/commission. A-shares require `akshare` (included in the `paper` extra).

For live reload during UI development, keep the API running and in another shell:

```bash
cd web
npm run dev
```

Then use http://localhost:5173 (Vite proxies `/api` to port 8000).

### News (Finnhub)

1. Register a free key at [finnhub.io/register](https://finnhub.io/register)
2. Copy `.env.example` to `.env` and set `FINNHUB_API_KEY` (`.env` is gitignored). You can also `export FINNHUB_API_KEY=...`.

```bash
quantit news --symbol AAPL
quantit news --symbol AAPL --watch --interval 30
```

Or run `python examples/news_feed.py`.

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
