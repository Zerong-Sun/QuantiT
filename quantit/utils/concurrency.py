"""Concurrency helpers for I/O-bound market-data fetches.

Network calls (Yahoo / AkShare / Eastmoney) dominate paper-tick latency, and a
local proxy can make each round-trip seconds long. Fetching symbols in parallel
turns ~N serial round-trips into ~ceil(N / workers) batches.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

_T = TypeVar("_T")
_R = TypeVar("_R")

_DEFAULT_WORKERS = 8
_MAX_WORKERS = 64


def fetch_workers() -> int:
    """Concurrent fetch threads, configurable via ``QUANTIT_FETCH_WORKERS``."""
    raw = os.environ.get("QUANTIT_FETCH_WORKERS", "").strip()
    if not raw:
        return _DEFAULT_WORKERS
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_WORKERS
    return min(max(parsed, 1), _MAX_WORKERS)


def parallel_map(
    func: Callable[[_T], _R],
    items: Iterable[_T],
    max_workers: int | None = None,
) -> list[_R]:
    """Run ``func`` over ``items`` in a thread pool, preserving input order.

    ``func`` is expected to be I/O bound and must not require shared mutable
    state (each provider ``fetch`` call is independent).
    """
    seq = list(items)
    workers = max_workers if max_workers is not None else fetch_workers()
    if workers <= 1 or len(seq) <= 1:
        return [func(item) for item in seq]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(func, seq))
