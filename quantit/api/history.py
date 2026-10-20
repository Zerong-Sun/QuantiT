"""Read-only access to isolated, versioned daily paper histories."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3

from fastapi import FastAPI, HTTPException


def history_root() -> Path:
    return Path(os.environ.get('QUANTIT_HISTORY_ROOT', str(Path.home()/'.quantit/history/2026-07-01')))


def read_report(root: Path) -> dict:
    path = root/'report.json'
    if not path.is_file():
        return {'ready': False, 'strategies': [], 'limitations': [], 'start': '2026-07-01'}
    return {'ready': True, **json.loads(path.read_text())}


def service_status(root: Path) -> dict:
    path = root/'service.json'
    if not path.is_file():
        return {'state': 'unknown', 'fresh': False}
    data = json.loads(path.read_text())
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(data['heartbeat'])).total_seconds()
        data['fresh'] = 0 <= age < 3600
    except (KeyError, TypeError, ValueError):
        data['fresh'] = False
    return data


def attach_history_routes(app: FastAPI) -> None:
    @app.get('/api/v1/history')
    def history():
        root = history_root()
        return {**read_report(root), 'service': service_status(root)}

    @app.get('/api/v1/history/{strategy}/{day}')
    def history_day(strategy: str, day: str):
        if not re.fullmatch(r'[a-z0-9_]+', strategy) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            raise HTTPException(404, 'Unknown history')
        root = history_root()
        report = read_report(root)
        record = next((s for s in report['strategies'] if s['id'] == strategy), None)
        if record is None or day not in {d['day'] for d in record.get('days', [])}:
            raise HTTPException(404, 'Unknown history day')
        path = root/'books'/f'{strategy}.db'
        if not path.is_file():
            raise HTTPException(404, 'History ledger unavailable')
        # Opening in read-only mode cannot create or migrate a trading database.
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as connection:
            row = connection.execute('SELECT detail FROM recovery_days WHERE day = ?', (day,)).fetchone()
        if row is None:
            raise HTTPException(404, 'History day unavailable')
        return json.loads(row[0])
