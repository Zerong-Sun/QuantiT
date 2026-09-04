"""Serve the paper terminal UI from web/dist, with a fallback page."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

_FALLBACK = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>QuantiT Paper Terminal</title>
    <style>
      body { font: 15px/1.5 -apple-system, sans-serif; background: #0b0f14; color: #e7ecf3;
             max-width: 40rem; margin: 12vh auto; padding: 0 1.5rem; }
      code { background: #1b2430; padding: 2px 6px; border-radius: 4px; }
      pre { background: #121821; padding: 1rem; border-radius: 8px; overflow: auto; }
      a { color: #4da3ff; }
    </style>
  </head>
  <body>
    <h1>QuantiT Paper Terminal</h1>
    <p>API is running. The UI bundle is missing — build it once, then refresh:</p>
    <pre>cd web
npm install
npm run build</pre>
    <p>Or in another terminal run <code>npm run dev</code> and open
      <a href="http://127.0.0.1:5173">http://127.0.0.1:5173</a>.</p>
    <p>Do not open <code>web/index.html</code> as a file; it needs a server.</p>
  </body>
</html>
"""


def frontend_dist() -> Path | None:
    env = os.environ.get("QUANTIT_WEB_DIST")
    candidates = []
    if env:
        candidates.append(Path(env))
    repo_web = Path(__file__).resolve().parents[2] / "web" / "dist"
    candidates.append(repo_web)
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return None


def mount_frontend(app: FastAPI) -> None:
    dist = frontend_dist()
    if dist is None:
        @app.get("/", include_in_schema=False)
        def ui_fallback() -> HTMLResponse:
            return HTMLResponse(_FALLBACK)

        @app.get("/portfolio", include_in_schema=False)
        def ui_portfolio_fallback() -> HTMLResponse:
            return HTMLResponse(_FALLBACK)

        @app.get("/research", include_in_schema=False)
        def ui_research_fallback() -> HTMLResponse:
            return HTMLResponse(_FALLBACK)

        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/", include_in_schema=False)
    def ui_index() -> FileResponse:
        return FileResponse(dist / "index.html")

    @app.get("/portfolio", include_in_schema=False)
    def ui_portfolio() -> FileResponse:
        return FileResponse(dist / "index.html")

    @app.get("/research", include_in_schema=False)
    def ui_research() -> FileResponse:
        return FileResponse(dist / "index.html")
