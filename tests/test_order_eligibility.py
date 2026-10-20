"""Exercise the UI guard that prevents orders using incomplete or stale selection data."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "web" / "src" / "orderEligibility.ts"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({}, True),
        ({"submitting": True}, False),
        ({"loading": True}, False),
        ({"quoteError": "行情刷新失败"}, False),
        ({"hasAccount": False}, False),
        ({"instrumentSymbol": "AAPL"}, False),
        ({"quoteSymbol": "AAPL"}, False),
        ({"instrumentSymbol": None}, False),
        ({"quoteSymbol": None}, False),
        ({"symbol": "", "quoteSymbol": "", "instrumentSymbol": ""}, False),
        ({"quantity": 0}, False),
        ({"quantity": -1}, False),
        ({"quantity": 1.5}, False),
        ({"last": None}, False),
        ({"last": 0}, False),
        ({"last": -1}, False),
        ({"last": float("inf")}, False),
        ({"quantity": float("nan")}, False),
    ],
)
def test_order_guard(change: dict, expected: bool) -> None:
    state = {
        "submitting": False,
        "loading": False,
        "quoteError": "",
        "hasAccount": True,
        "symbol": "JNJ",
        "instrumentSymbol": "JNJ",
        "quoteSymbol": "JNJ",
        "quantity": 10,
        "last": 250,
        **change,
    }
    # json.dumps' Infinity/NaN are valid JavaScript literals for these boundary cases.
    script = (
        f"import {{ canSubmitOrder }} from {json.dumps(str(HELPER))};"
        f"process.stdout.write(String(canSubmitOrder({json.dumps(state)})));"
    )
    result = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(expected).lower()
