"""Auditable, date-capped reconstruction of interrupted paper books.

Works on an explicit database copy. No broker feed is used during replay.
Today's parameters are frozen for the run; this is a reconstruction, not
evidence of orders actually executed on those historical dates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd

from quantit.data.cache import DataCache
from quantit.data.macro import DEFAULT_MACRO_SYMBOLS
from quantit.data.provider import YahooFinanceProvider
from quantit.features.cn_regime import compute_cn_etf_scores
from quantit.features.regime import compute_theme_scores
from quantit.markets.assets import multiplier
from quantit.markets.cn import CNAdapter, CN_ETF_FALLBACK, all_cn_etf_symbols
from quantit.markets.hk import HKAdapter, all_hstech_symbols
from quantit.markets.registry import MarketRegistry, default_registry
from quantit.markets.types import Quote
from quantit.markets.us import USAdapter
from quantit.paper.books import DESK_BOOK_IDS, venue_of
from quantit.paper.broker import PaperBroker
from quantit.paper.capital import HK_ETF_WATCHLIST, HK_WARRANT_WATCHLIST
from quantit.paper.db import create_session
from quantit.paper.models import RecoveryDay
from quantit.paper.runner import PaperRunner
from quantit.research.params import strategy_params
from quantit.research.universes import CN_QUALITY, HK_QUALITY, US_QUALITY
from quantit.utils.concurrency import parallel_map


BOOK_SYMBOLS = {
    "us": US_QUALITY, "us_book": US_QUALITY, "hk": HK_QUALITY,
    "hk_theme": (*all_hstech_symbols(), *HK_ETF_WATCHLIST, *HK_WARRANT_WATCHLIST),
    "cn": CN_QUALITY, "cn_etf": (*all_cn_etf_symbols(), CN_ETF_FALLBACK),
}
REFERENCES = {"us": "SPY", "hk": "0700.HK", "cn": CN_ETF_FALLBACK}


def session_close(day: pd.Timestamp, venue: str) -> datetime:
    zone, hour = {"us": ("America/New_York", 16), "hk": ("Asia/Hong_Kong", 16),
                  "cn": ("Asia/Shanghai", 15)}[venue]
    return datetime.combine(day.date(), time(hour, 5), ZoneInfo(zone)).astimezone(timezone.utc).replace(tzinfo=None)


def copy_database(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError("Recovery destination must be a new database, separate from the source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)


def download_bundle(broker: PaperBroker, root: Path, start: str, end: str) -> dict:
    """Fetch once, record coverage/errors, and freeze the exact replay input."""
    root.mkdir(parents=True, exist_ok=True)
    registry = default_registry()
    requests = {(venue_of(book), sym) for book, symbols in BOOK_SYMBOLS.items() for sym in symbols}
    requests.update((venue_of(p.market_id), p.symbol) for p in broker.list_positions() if p.market_id != "cl")
    requests.update(REFERENCES.items())
    requests.update(("macro", symbol) for symbol in DEFAULT_MACRO_SYMBOLS.values())
    begin = (pd.Timestamp(start) - pd.Timedelta(days=600)).strftime("%Y-%m-%d")
    finish = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    def fetch(item):
        venue, symbol = item
        path = root / f"{venue}_{symbol.replace('^', '_').replace('=', '_')}.parquet"
        try:
            if path.exists():
                frame = pd.read_parquet(path)
            else:
                try:
                    frame = YahooFinanceProvider().fetch(symbol, begin, finish)
                except ValueError:
                    if venue == "macro":
                        raise
                    frame = registry.get(venue).fetch_bars(symbol, "1d", begin, finish)
                frame = frame.sort_index()
                frame = frame[~frame.index.duplicated(keep="last")]
                frame.to_parquet(path)
                cache = DataCache()
                existing = cache.get(symbol)
                combined = pd.concat([existing, frame]) if existing is not None else frame
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                cache.set(symbol, combined)
            return symbol, {
                "venue": venue, "file": path.name, "rows": len(frame),
                "first": str(frame.index.min().date()), "last": str(frame.index.max().date()),
            }
        except Exception as exc:
            return symbol, {"venue": venue, "error": str(exc)}

    manifest = dict(parallel_map(fetch, sorted(requests), max_workers=6))
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


class HistoricalAdapter:
    """Delegate venue rules; cap both signal bars and fills to one closed session."""

    def __init__(self, base, frames: dict[str, pd.DataFrame], day: pd.Timestamp):
        self.base, self.frames, self.day = base, frames, day

    def __getattr__(self, name):
        return getattr(self.base, name)

    def fetch_bars(self, symbol, interval, start, end):
        if interval != "1d":
            raise ValueError("Historical recovery only supports daily bars")
        symbol = self.normalize_symbol(symbol)
        if symbol not in self.frames:
            raise ValueError(f"No historical data: {symbol}")
        frame = self.frames[symbol]
        cutoff = min(pd.Timestamp(end).tz_localize(None), self.day)
        return frame.loc[(frame.index >= pd.Timestamp(start).tz_localize(None)) & (frame.index <= cutoff)].copy()

    def fetch_quote(self, symbol):
        symbol = self.normalize_symbol(symbol)
        frame = self.fetch_bars(symbol, "1d", self.day - pd.Timedelta(days=14), self.day)
        if frame.empty or frame.index[-1].normalize() != self.day:
            raise ValueError(f"No exact-session quote: {symbol} on {self.day.date()}")
        row = frame.iloc[-1]
        last = float(row["close"])
        prev = float(frame.iloc[-2]["close"]) if len(frame) > 1 else last
        return Quote(
            symbol=symbol, market_id=self.market_id, last=last, open=float(row["open"]),
            high=float(row["high"]), low=float(row["low"]), prev_close=prev,
            volume=float(row["volume"]), change=last-prev,
            change_pct=100*(last/prev-1) if prev else 0,
            timestamp=self.day.to_pydatetime(), delayed=True,
        )


class ReconstructionBroker(PaperBroker):
    def place_order(self, market_id, symbol, side, quantity, rationale=None):
        return super().place_order(
            market_id, symbol, side, quantity,
            rationale=f"[historical reconstruction] {rationale or ''}",
        )


def replay(broker: PaperBroker, root: Path, start: str, end: str, books=DESK_BOOK_IDS) -> list[dict]:
    if pd.Timestamp(start) > pd.Timestamp(end):
        raise ValueError("start must be on or before end")
    if set(books) - set(DESK_BOOK_IDS):
        raise ValueError("Only desk books can be recovered; Closeloop is separate")
    manifest = json.loads((root / "manifest.json").read_text())
    frames = {symbol: pd.read_parquet(root / row["file"]) for symbol, row in manifest.items() if "file" in row}
    macro_parts = [
        frames[s]["close"].rename(name) for name, s in DEFAULT_MACRO_SYMBOLS.items() if s in frames
    ]
    macros = pd.concat(macro_parts, axis=1).sort_index() if macro_parts else pd.DataFrame()
    # US daily closes are not known at the same date's Asian close.
    macros = macros.shift(1).ffill()
    hk_scores = compute_theme_scores({s: frames[s] for s in all_hstech_symbols() if s in frames}, macros)
    cn_scores = compute_cn_etf_scores({s: frames[s] for s in BOOK_SYMBOLS["cn_etf"] if s in frames}, macros)
    audit = {
        "replay_version": 2,
        "start": start, "end": end, "books": list(books),
        "inputs": {
            symbol: hashlib.sha256((root / row["file"]).read_bytes()).hexdigest()
            if "file" in row else row
            for symbol, row in manifest.items()
        },
        "mode": "historical paper reconstruction; frozen current parameters; delayed-close analog",
        "parameters": {name: strategy_params(name) for name in (
            "tsmom", "us_book", "hk_quality_book", "theme_rotation", "cn_quality_book", "cn_etf_rotation")},
        "unavailable_symbols": {s: r for s, r in manifest.items() if "error" in r},
        "derivatives": "Existing positions require historical marks; no newly selected option overlays",
    }
    protocol_path = root / "protocol.json"
    if protocol_path.exists():
        previous_protocol = json.loads(protocol_path.read_text())
        if previous_protocol.get("parameters") != audit["parameters"]:
            raise ValueError("Parameters changed since this recovery bundle was frozen")
        for key in ("replay_version", "start", "end", "books", "inputs"):
            if previous_protocol.get(key) != audit[key]:
                raise ValueError(f"Recovery protocol changed ({key}); use a new bundle and database copy")
    protocol_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=str))
    results = []
    for book in books:
        venue = venue_of(book)
        ref = frames.get(REFERENCES[venue])
        if ref is None:
            results.append({"book": book, "status": "blocked", "error": "Missing venue calendar"})
            continue
        trades = broker.list_trades(book)
        last_trade = max((t.timestamp.date() for t in trades), default=None)
        days = ref.index[(ref.index >= pd.Timestamp(start)) & (ref.index <= pd.Timestamp(end))]
        for day in days:
            key = (book, str(day.date()))
            previous = broker.session.get(RecoveryDay, key)
            if previous:
                if previous.status == "complete":
                    continue
                results.append({"book": book, "day": key[1], "status": "blocked", "error": previous.detail})
                break  # Never replay a partial day blindly.
            if last_trade and day.date() <= last_trade:
                continue
            adapters = MarketRegistry()
            for cls in (USAdapter, HKAdapter, CNAdapter):
                adapters.register(HistoricalAdapter(cls(), frames, day))
            historical = ReconstructionBroker(
                broker.session, adapters, now=lambda d=day, v=venue: session_close(d, v)
            )
            row = RecoveryDay(market_id=book, day=key[1], status="started", detail="Interrupted days require review")
            broker.session.add(row)
            broker.session.commit()
            try:
                adapter = historical.adapter_for(book)
                # Never size from incomplete held marks or invent an expired option settlement.
                held = {p.symbol for p in historical.list_positions(book)}
                required = held | (set(BOOK_SYMBOLS[book]) if book in {"us", "us_book", "hk", "cn"} else set())
                for symbol in sorted(required):
                    adapter.fetch_quote(symbol)
                runner = PaperRunner(
                    historical, hk_scores=hk_scores.loc[:day], cn_scores=cn_scores.loc[:day],
                    recovery_mode=True,
                )
                actions = runner.tick(markets=(book,))
                if runner.last_error:
                    raise ValueError(runner.last_error)
                if any(a["status"] != "filled" for a in actions):
                    raise ValueError(f"Rejected historical orders: {actions}")
                row.equity = historical.get_account(book).cash + sum(
                    p.quantity * adapter.fetch_quote(p.symbol).last * multiplier(venue, p.symbol)
                    for p in historical.list_positions(book)
                )
                row.status = "complete"
                row.detail = json.dumps({"orders": len(actions), "reconstruction": True})
            except Exception as exc:
                row.status, row.detail = "blocked", str(exc)
            broker.session.commit()
            results.append({"book": book, "day": key[1], "status": row.status, "equity": row.equity, "detail": row.detail})
            if row.status != "complete":
                break
    # The return value describes work done now; the export is the durable ledger.
    # A no-op resume must not erase the evidence from an earlier successful run.
    ledger = [
        {"book": row.market_id, "day": row.day, "status": row.status,
         "equity": row.equity, "detail": row.detail}
        for row in broker.session.query(RecoveryDay).order_by(
            RecoveryDay.market_id, RecoveryDay.day
        ).all()
    ]
    ledger.extend(item for item in results if "day" not in item)
    result_path = root / "result.json"
    temporary = result_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2))
    temporary.replace(result_path)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.home()/".quantit/paper.db")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if not args.output.exists():
        copy_database(args.source, args.output)
    elif args.output.resolve() == args.source.resolve():
        parser.error("output must be separate from source")
    broker = PaperBroker(create_session(f"sqlite:///{args.output.resolve()}"))
    if args.download:
        download_bundle(broker, args.data_dir, args.start, args.end)
    results = replay(broker, args.data_dir, args.start, args.end)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
