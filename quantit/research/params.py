"""Promoted research parameters (YAML). Runner/signals read; never written by LLM briefs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_CACHE: dict[str, Any] | None = None
_CACHE_KEY: str | None = None
_CACHE_MTIME: float | None = None


def research_dir() -> Path:
    raw = os.environ.get("QUANTIT_RESEARCH_DIR")
    if raw:
        return Path(raw)
    return Path.home() / ".quantit" / "research"


def active_params_path() -> Path:
    override = os.environ.get("QUANTIT_ACTIVE_PARAMS")
    if override:
        return Path(override)
    return research_dir() / "active_params.yaml"


def clear_params_cache() -> None:
    global _CACHE, _CACHE_KEY, _CACHE_MTIME
    _CACHE = None
    _CACHE_KEY = None
    _CACHE_MTIME = None


def load_active_params(path: str | Path | None = None) -> dict[str, Any]:
    """Return the promote file, or {} if missing/invalid."""
    global _CACHE, _CACHE_KEY, _CACHE_MTIME
    target = Path(path) if path is not None else active_params_path()
    key = str(target)
    mtime = target.stat().st_mtime if target.is_file() else -1.0
    if _CACHE is not None and _CACHE_KEY == key and _CACHE_MTIME == mtime:
        return _CACHE
    if not target.is_file():
        _CACHE, _CACHE_KEY, _CACHE_MTIME = {}, key, mtime
        return _CACHE
    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        payload = {}
    _CACHE, _CACHE_KEY, _CACHE_MTIME = payload, key, mtime
    return payload


def strategy_params(strategy_id: str, path: str | Path | None = None) -> dict[str, Any]:
    data = load_active_params(path)
    block = (data.get("strategies") or {}).get(strategy_id) or {}
    return dict(block) if isinstance(block, dict) else {}


def us_primary(path: str | Path | None = None) -> str:
    data = load_active_params(path)
    value = data.get("us_primary") or "us_book"
    return str(value)


def hk_primary(path: str | Path | None = None) -> str:
    data = load_active_params(path)
    value = data.get("hk_primary") or "theme_rotation"
    return str(value)


def cn_primary(path: str | Path | None = None) -> str:
    data = load_active_params(path)
    value = data.get("cn_primary") or "cn_etf_rotation"
    return str(value)


def write_active_params(payload: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else active_params_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    clear_params_cache()
    return target
