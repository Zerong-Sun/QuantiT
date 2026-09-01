# QuantiT

A research-oriented quantitative trading platform for US equities and Hong Kong long-horizon strategies. US path: technical factors and event-driven backtesting, with optional news polling for research (no live trading). HK path: Hang Seng TECH / Chinese internet theme rotation from supply-demand, policy regimes, and international macros — no news sentiment, no high-frequency trading.

## Current capabilities

- **Data**: Yahoo Finance OHLCV with Parquet caching (gap-aware); HK `.HK` names and macro series
- **Factors**: Technical indicators (SMA, EMA, RSI, MACD, Bollinger, ATR, momentum, volatility)
- **Strategies**: Moving-average crossover and RSI mean reversion (single symbol); HK monthly theme rotation (multi-asset)
- **Backtest**: Bar-by-bar simulation; single-name signals fill on the next bar's open by default
- **Analysis**: Performance metrics, Plotly charts, HTML reports
- **News**: Finnhub REST polling for company and general market headlines (US research/testing only; not used by the HK regime path)

ML, RL, and a Streamlit dashboard are not implemented yet.

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
quantit/          # Core library
examples/         # Example strategies
tests/            # Unit tests
knowledge_base/   # Theory notes (not a feature checklist)
```

Optional extras (not required for backtests):

```bash
pip install -e ".[ml]"         # torch, xgboost, sklearn, …
pip install -e ".[dashboard]"  # streamlit (planned)
```

## License

MIT
