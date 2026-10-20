#!/usr/bin/env python3
"""Independently reconcile exported daily histories against their SQLite ledgers."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sqlite3


def check(root: Path) -> dict:
    report = json.loads((root / "report.json").read_text())
    results = []
    for strategy in report["strategies"]:
        name = strategy["id"]
        with sqlite3.connect(f"file:{root / 'books' / (name + '.db')}?mode=ro", uri=True) as db:
            days = [json.loads(row[0]) for row in db.execute("SELECT detail FROM recovery_days ORDER BY day")]
            trades = db.execute("SELECT symbol, side, quantity, price, commission FROM trades ORDER BY id").fetchall()
            orders = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            actual_positions = dict(db.execute("SELECT symbol, quantity FROM positions WHERE quantity > 0"))
            lots = dict(db.execute(
                "SELECT p.symbol, SUM(l.remaining) FROM positions p JOIN position_lots l "
                "ON l.position_id = p.id GROUP BY p.symbol HAVING SUM(l.remaining) > 0"))
        assert strategy["status"] == "ready", (name, strategy.get("error"))
        assert len(days) == strategy["sessions"] > 0, name
        assert len({d["day"] for d in days}) == len(days), name
        assert [d["day"] for d in days] == [d["day"] for d in strategy["days"]], name
        cash = strategy["initial_cash"]
        equity = cash
        peak = cash
        receivable = 0.0
        positions = defaultdict(int)
        fills = []
        for day, exported in zip(days, strategy["days"]):
            context = (name, day["day"])
            assert report["start"] <= day["day"] <= report["requested_end"], context
            assert day["signal_through"] < day["day"], context
            for event in day["corporate_actions"]:
                if event["type"] == "split":
                    # Fractional share entitlements need a separate lot-level
                    # audit; fail explicitly rather than silently rounding them.
                    expanded = positions[event["symbol"]] * event["ratio"]
                    assert math.isclose(expanded, round(expanded), abs_tol=1e-6), (context, event)
                    positions[event["symbol"]] = round(expanded)
                elif event["type"] == "dividend_receivable":
                    receivable += event["amount"]
                else:
                    raise AssertionError((context, event))
            for order in day["orders"]:
                if order["status"] != "filled":
                    assert order["fee"] == 0, (context, order)
                    continue
                assert order["quantity"] > 0 and order["price"] > 0 and order["fee"] >= 0, (context, order)
                direction = 1 if order["side"] == "buy" else -1
                positions[order["symbol"]] += direction * order["quantity"]
                cash -= direction * order["quantity"] * order["price"] + order["fee"]
                fills.append((order["symbol"], order["side"], order["quantity"], order["price"], order["fee"]))
            expected = {s: q for s, q in positions.items() if q}
            assert all(q >= 0 for q in expected.values()), context
            assert expected == {p["symbol"]: p["quantity"] for p in day["positions"]}, context
            assert cash >= -1e-6 and math.isclose(cash, day["cash"], abs_tol=1e-6), context
            assert math.isclose(receivable, day["receivable"], abs_tol=1e-6), context
            value = sum(p["quantity"] * p["close"] for p in day["positions"])
            for position in day["positions"]:
                assert position["price_date"] <= day["day"], context
                assert math.isclose(position["value"], position["quantity"] * position["close"], abs_tol=1e-6), context
            current = cash + receivable + value
            peak = max(peak, current)
            for field, expected_value in {
                "equity": current, "daily_pnl": current - equity,
                "drawdown": current / peak - 1,
                "total_return": current / strategy["initial_cash"] - 1,
                "fees": sum(o["fee"] for o in day["orders"]),
                "fills": sum(o["status"] == "filled" for o in day["orders"]),
            }.items():
                assert math.isclose(day[field], expected_value, abs_tol=1e-6), (context, field)
                assert exported[field] == day[field], (context, field, "export")
            equity = current
        assert sorted(fills) == sorted(trades), (name, "trade reconciliation")
        assert orders == sum(len(d["orders"]) for d in days), (name, "order reconciliation")
        assert actual_positions == expected == lots, (name, "position/lot reconciliation")
        assert strategy["fills"] == len(trades), name
        assert math.isclose(strategy["fees"], sum(t[4] for t in trades), abs_tol=1e-6), name
        assert strategy["last_day"] == days[-1]["day"], name
        assert math.isclose(strategy["equity"], equity, abs_tol=1e-6), name
        results.append({
            "id": name, "sessions": len(days), "fills": len(trades), "orders": orders,
            "equity": equity, "last_day": days[-1]["day"],
            "ledger_sha256": hashlib.sha256(json.dumps(days, sort_keys=True).encode()).hexdigest(),
        })
    return {"passed": True, "book_count": len(results),
            "book_days": sum(x["sessions"] for x in results), "strategies": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / ".quantit/history/2026-07-01")
    args = parser.parse_args()
    print(json.dumps(check(args.root), ensure_ascii=False, indent=2))
