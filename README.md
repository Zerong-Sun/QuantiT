# QuantiT

A research-oriented quantitative trading platform for US equities. Supports technical, factor, ML, and RL strategies with event-driven backtesting.

## Features

- **Data Layer**: Yahoo Finance integration with Parquet caching
- **Factor Engine**: Technical and fundamental factor library
- **Strategy Layer**: Technical, factor, ML, and RL strategies
- **Backtest Engine**: Event-driven simulation with portfolio and risk management
- **Analysis**: Performance metrics, Plotly charts, HTML reports
- **Dashboard**: Streamlit web interface

## Quick Start

```bash
pip install -e ".[dev]"

# Run MA crossover backtest
python examples/ma_crossover.py

# Launch dashboard
streamlit run dashboard/app.py
```

## Project Structure

```
quantit/          # Core library
examples/         # Example strategies
notebooks/        # Jupyter research notebooks
dashboard/        # Streamlit dashboard
tests/            # Unit tests
```

## License

MIT
