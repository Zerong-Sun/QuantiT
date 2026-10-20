"""Refresh the existing fixed research universe into a new, versioned dump.

This does not claim point-in-time CSI300 membership. All adjusted history is
refetched to avoid splicing incompatible adjustment bases. Incomplete input
never replaces the currently active dump. A staged panel may contain missing
latest rows, explicitly reported in coverage; those rows are never fabricated.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from closeloop.data.ingest import attach_cap, panel_from_csv_dir, write_qlib_layout


def refresh(source: Path, destination: Path, end: str, workers: int = 4) -> dict:
    if source.resolve() == destination.resolve():
        raise ValueError("Use a separate destination; preserve the active research dump")
    old = pd.read_parquet(source / "panel.parquet")
    instruments = sorted(old["close"].columns)
    start = str(old.index.min().date())
    raw = destination / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    def one(instrument):
        import yfinance as yf

        path = raw / f"{instrument}.csv"
        try:
            if path.exists():
                bars = pd.read_csv(path, parse_dates=["date"]).set_index("date")
            else:
                suffix = ".SS" if instrument.startswith("SH") else ".SZ"
                bars = yf.Ticker(instrument[2:] + suffix).history(
                    start=start, end=str((pd.Timestamp(end)+pd.Timedelta(days=1)).date()),
                    auto_adjust=True, timeout=15,
                )
                bars = bars.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
                bars.index = pd.DatetimeIndex(bars.index).tz_localize(None)
                bars.index.name = "date"
                bars.to_csv(path)
            if bars.empty or bars.index.max().normalize() < pd.Timestamp(end):
                import akshare as ak

                bars = ak.stock_zh_a_hist_tx(
                    symbol=instrument.lower(), start_date=start.replace("-", ""),
                    end_date=end.replace("-", ""), adjust="qfq", timeout=15,
                )
                bars = bars.set_index(pd.to_datetime(bars["date"]))[
                    ["open", "high", "low", "close", "volume"]
                ].astype(float).sort_index()
                bars.index.name = "date"
                if bars.empty or bars.index.max().normalize() < pd.Timestamp(end):
                    raise ValueError(f"Missing requested end date {end}, including fallback")
                bars.to_csv(path)
            return {"instrument": instrument, "rows": len(bars), "last": str(bars.index.max().date())}
        except Exception as exc:
            return {"instrument": instrument, "error": str(exc)}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(one, instruments))
    report = {"start": start, "end": end, "universe": "fixed existing research universe",
              "instruments": len(instruments), "results": rows,
              "complete": all("error" not in row for row in rows)}
    report["latest_coverage"] = sum("error" not in row for row in rows)/len(rows)
    report["usable"] = report["latest_coverage"] >= 0.95 and all(
        (raw/f"{inst}.csv").exists() and len(pd.read_csv(raw/f"{inst}.csv")) > 0 for inst in instruments
    )
    (destination/"refresh.json").write_text(json.dumps(report, indent=2))
    if report["usable"]:
        panel = attach_cap(panel_from_csv_dir(raw))
        # Preserve supplied industry classifications, never synthesize new ones.
        if "industry" in old.columns.get_level_values("field"):
            industry = old["industry"].reindex(panel.index).ffill()
            industry.columns = pd.MultiIndex.from_product(
                [["industry"], industry.columns], names=["field", "instrument"]
            )
            panel = pd.concat([panel, industry], axis=1).sort_index(axis=1)
        write_qlib_layout(panel, destination)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    report = refresh(args.source, args.destination, args.end)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["usable"] else 1)
