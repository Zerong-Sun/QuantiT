"""HTML-as-JSON guard used by the paper UI client (`web/src/api.ts`)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "web" / "src" / "jsonResponse.ts"
HTML_ERROR_SNIPPET = "API 返回了 HTML 而不是 JSON"
SERVE_HINT = "http://127.0.0.1:8000/"


def _run_assert(content_type: str, body: str) -> subprocess.CompletedProcess[str]:
    script = f"""
import {{ assertJsonResponse }} from {json.dumps(HELPER.resolve().as_posix())};
try {{
  assertJsonResponse({json.dumps(content_type)}, {json.dumps(body)});
  process.stdout.write("ok");
}} catch (err) {{
  process.stdout.write("err:" + (err instanceof Error ? err.message : String(err)));
  process.exitCode = 2;
}}
"""
    return subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_helper_module_exists() -> None:
    assert HELPER.is_file(), f"missing {HELPER.relative_to(ROOT)}"


def test_getjson_uses_helper_before_parse() -> None:
    src = (ROOT / "web" / "src" / "api.ts").read_text(encoding="utf-8")
    fn = src.split("async function getJson", 1)[1].split("function formatApiError", 1)[0]
    assert "assertJsonResponse" in fn
    assert fn.index("assertJsonResponse") < fn.index("JSON.parse")
    assert "res.json(" not in fn


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("application/json", '{"ok": true}'),
        ("application/json; charset=utf-8", "[1, 2]"),
        ("", '{"detail": "Not Found"}'),
        ("application/json", "  {\"n\": 1}"),
    ],
)
def test_assert_json_response_allows_json(content_type: str, body: str) -> None:
    proc = _run_assert(content_type, body)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout == "ok"


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("text/html", '{"ok": true}'),
        ("text/html; charset=utf-8", "<!doctype html><html></html>"),
        ("Text/HTML", "not html looking"),
        ("application/json", "<!DOCTYPE html><html lang=en>"),
        ("application/json", "  <html><body>spa</body></html>"),
        ("", "<!doctype html>"),
        ("application/json", "\n<html>"),
    ],
)
def test_assert_json_response_rejects_html(content_type: str, body: str) -> None:
    proc = _run_assert(content_type, body)
    assert proc.returncode != 0, proc.stdout
    assert proc.stdout.startswith("err:")
    message = proc.stdout[len("err:") :]
    assert HTML_ERROR_SNIPPET in message
    assert SERVE_HINT in message
    assert "quantit serve" in message
    assert "Vite" in message or "vite" in message
    # Must not look like JSON.parse's "Unexpected token '<'"
    assert "Unexpected token" not in message
