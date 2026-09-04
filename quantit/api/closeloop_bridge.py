"""FastAPI bridge: closeloop worker + paper account ``cl`` only.

The only quantit module allowed to import closeloop.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from closeloop.library import load_library
from closeloop.loop.book import TargetBook
from closeloop.loop.feedback import default_trace_path
from closeloop.loop.worker import LoopWorker, dump_exists, parquet_exists
from closeloop.model.dataset import build_dataset
from closeloop.model.train import train_predict_ic
from quantit.paper.broker import PaperBroker


def make_worker() -> LoopWorker:
    force = os.environ.get("CLOSELOOP_FIXTURE", "").strip() in {"1", "true", "yes"}
    if not force and not dump_exists():
        force = True
    return LoopWorker(force_fixture=force)


def _unit_cost(adapter, quote) -> float:
    px = float(quote.last)
    fill = px * (1.0 + float(adapter.profile.slippage_rate))
    rate = float(adapter.profile.all_in_commission_rate)
    return fill * (1.0 + rate)


def _cl_marks(broker: PaperBroker) -> tuple[float | None, float | None]:
    if "cl" not in broker.registry.ids():
        return None, None
    try:
        cash = float(broker.get_account("cl").cash)
    except KeyError:
        return None, None
    invested = 0.0
    adapter = broker.registry.get("cl")
    for pos in broker.list_positions("cl"):
        if pos.quantity <= 0:
            continue
        try:
            last = float(adapter.fetch_quote(pos.symbol).last)
        except (ValueError, KeyError):
            last = float(pos.avg_cost)
        invested += float(pos.quantity) * last
    return cash, cash + invested


def apply_target_book(broker: PaperBroker, book: TargetBook, rationale: str | None = None) -> list[dict[str, Any]]:
    """Delta-rebalance the ``cl`` book only. Never touches us/hk/cn.

    Same-day T+1 lots are left in place instead of flatten-and-rebuy, so a second
    step cannot double the research sleeve.
    """
    if "cl" not in broker.registry.ids():
        return []
    note = rationale or book.rationale
    adapter = broker.registry.get("cl")
    produced: list[dict[str, Any]] = []

    def _record(order) -> None:
        produced.append(
            {
                "symbol": order.symbol,
                "side": order.side,
                "status": order.status,
                "qty": order.quantity,
                "reject_reason": order.reject_reason,
            }
        )

    quotes: dict[str, Any] = {}

    def quote_of(symbol: str):
        if symbol not in quotes:
            quotes[symbol] = adapter.fetch_quote(symbol)
        return quotes[symbol]

    current = {p.symbol: int(p.quantity) for p in broker.list_positions("cl") if p.quantity > 0}
    for symbol, qty in list(current.items()):
        if symbol in book.weights:
            continue
        pos = broker.get_position("cl", symbol)
        if pos is None:
            continue
        sellable = broker._sellable_qty(pos, broker.now(), adapter.t_plus)
        lot = adapter.lot_size(symbol)
        qty_out = int(sellable // lot) * lot
        if qty_out < lot:
            continue
        _record(broker.place_order("cl", symbol, "sell", qty_out, rationale=note))

    current = {p.symbol: int(p.quantity) for p in broker.list_positions("cl") if p.quantity > 0}
    cash, equity = _cl_marks(broker)
    if cash is None or equity is None or equity <= 0:
        return produced
    sleeve = float(equity)

    for symbol, weight in book.weights.items():
        try:
            quote = quote_of(symbol)
        except ValueError:
            continue
        unit = _unit_cost(adapter, quote)
        if unit <= 0:
            continue
        lot = adapter.lot_size(symbol)
        desired = int((sleeve * float(weight) / unit) // lot) * lot
        held = current.get(symbol, 0)
        if desired > held:
            affordable = int((float(broker.get_account("cl").cash) / unit) // lot) * lot
            qty_in = min(desired - held, affordable)
            qty_in = int(qty_in // lot) * lot
            if qty_in < lot:
                continue
            _record(broker.place_order("cl", symbol, "buy", qty_in, rationale=note))
        elif held > desired:
            pos = broker.get_position("cl", symbol)
            if pos is None:
                continue
            sellable = broker._sellable_qty(pos, broker.now(), adapter.t_plus)
            qty_out = min(held - desired, sellable)
            qty_out = int(qty_out // lot) * lot
            if qty_out < lot:
                continue
            _record(broker.place_order("cl", symbol, "sell", qty_out, rationale=note))
    return produced


def attach_closeloop_routes(app: FastAPI, broker: PaperBroker, worker: LoopWorker) -> None:
    def _with_book(status: dict[str, Any]) -> dict[str, Any]:
        cash, equity = _cl_marks(broker)
        status["cl_cash"] = cash
        status["cl_equity"] = equity
        status["cl_currency"] = "CNY"
        status["has_dump"] = parquet_exists(worker.data_dir)
        return status

    @app.get("/api/v1/closeloop/status")
    def closeloop_status() -> dict[str, Any]:
        return _with_book(worker.status().to_dict())

    @app.post("/api/v1/closeloop/start")
    def closeloop_start() -> dict[str, Any]:
        worker.start_background()
        return closeloop_status()

    @app.post("/api/v1/closeloop/stop")
    def closeloop_stop() -> dict[str, Any]:
        worker.stop()
        return closeloop_status()

    @app.post("/api/v1/closeloop/step")
    def closeloop_step() -> dict[str, Any]:
        status, target = worker.step()
        fills: list[dict[str, Any]] = []
        if target is not None and status.can_trade and status.passed:
            fills = apply_target_book(broker, target)
        payload = _with_book(status.to_dict())
        payload["fills"] = fills
        return payload

    @app.get("/api/v1/closeloop/library")
    def closeloop_library() -> list[dict[str, Any]]:
        return load_library(worker.artifacts_dir)

    @app.get("/api/v1/closeloop/trace")
    def closeloop_trace(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
        path = default_trace_path(worker.artifacts_dir)
        if not path.is_file():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows[-limit:]

    @app.get("/api/v1/closeloop/train")
    def closeloop_train(ids: str = "006,012,041") -> dict[str, Any]:
        try:
            plane = worker._plane()
            panel = plane.load_panel(worker.start, worker.end)
            alpha_ids = tuple(x.strip().zfill(3) for x in ids.split(",") if x.strip())[:8]
            ds = build_dataset(panel, alpha_ids=alpha_ids, horizon=1)
            return train_predict_ic(ds)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/closeloop/sidecar")
    def closeloop_sidecar() -> dict[str, Any]:
        seen = len(worker._seen_inbox)
        status, _ = worker.step(inbox_only=True)
        payload = _with_book(status.to_dict())
        payload["processed"] = max(0, len(worker._seen_inbox) - seen)
        return payload
