"""closeloop and quantit must not import each other's runtime surfaces."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_FROM_CLOSELOOP = (
    "quantit.paper",
    "quantit.markets",
    "quantit.strategy",
    "quantit.engine",
    "quantit.api",
    "quantit.data",
    "quantit.research",
    "quantit.features",
)


def _iter_py(package_dir: Path) -> list[Path]:
    return sorted(p for p in package_dir.rglob("*.py") if p.is_file())


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_closeloop_package_exists():
    assert (ROOT / "closeloop" / "__init__.py").is_file()


def test_closeloop_does_not_import_quantit_runtime():
    hits: list[str] = []
    for path in _iter_py(ROOT / "closeloop"):
        for name in _imported_modules(path):
            if name == "quantit" or name.startswith("quantit."):
                hits.append(f"{path.relative_to(ROOT)}: {name}")
            for banned in FORBIDDEN_FROM_CLOSELOOP:
                if name == banned or name.startswith(banned + "."):
                    hits.append(f"{path.relative_to(ROOT)}: {name}")
    assert hits == [], "closeloop imported quantit runtime:\n" + "\n".join(hits)


def test_quantit_does_not_import_closeloop():
    hits: list[str] = []
    allowed = {(ROOT / "quantit" / "api" / "closeloop_bridge.py").resolve()}
    for path in _iter_py(ROOT / "quantit"):
        if path.resolve() in allowed:
            continue
        for name in _imported_modules(path):
            if name == "closeloop" or name.startswith("closeloop."):
                hits.append(f"{path.relative_to(ROOT)}: {name}")
    assert hits == [], "quantit imported closeloop outside quantit/api/closeloop_bridge.py:\n" + "\n".join(hits)
