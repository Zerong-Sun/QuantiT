#!/usr/bin/env python3
"""Resident local service supervisor; launchd keeps this watchdog alive."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
stop = threading.Event()


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            return json.load(response).get("status") == "ok"
    except Exception:
        return False


def main() -> None:
    logdir = Path.home()/".quantit/runners"
    logdir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[RotatingFileHandler(logdir/"watchdog.log", maxBytes=1_000_000, backupCount=3)],
        format="%(asctime)s %(levelname)s %(message)s",
    )
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    env = dict(os.environ)
    env.setdefault("QUANTIT_LOG_FILE", str(logdir/"backend.log"))
    port = int(env.get("QUANTIT_BACKEND_PORT", "8000"))
    while not stop.is_set():
        child = subprocess.Popen(
            [sys.executable, "-m", "quantit.cli", "serve", "--host", "127.0.0.1",
             "--port", str(port), "--no-open"],
            cwd=ROOT, env=env, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        )
        logging.info("Started backend pid=%s", child.pid)
        misses = 0
        try:
            while not stop.wait(20):
                if child.poll() is not None:
                    logging.error("Backend exited code=%s", child.returncode)
                    break
                misses = 0 if healthy(port) else misses + 1
                if misses >= 3:
                    logging.error("Three HTTP health failures; restarting backend")
                    break
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
        stop.wait(3)


if __name__ == "__main__":
    main()
