"""Port LISTEN health check for paper UI runners."""

from __future__ import annotations

import os
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_runners.sh"


def _listen(host: str = "127.0.0.1") -> Iterator[tuple[socket.socket, int]]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, 0))
    sock.listen(1)
    port = int(sock.getsockname()[1])
    try:
        yield sock, port
    finally:
        sock.close()


def _run(
    *args: str,
    backend: int | None = None,
    vite: int | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if backend is not None:
        env["QUANTIT_BACKEND_PORT"] = str(backend)
    if vite is not None:
        env["QUANTIT_VITE_PORT"] = str(vite)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_check_runners_script_exists() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_both_required_ports_down_exits_nonzero() -> None:
    proc = _run(backend=59901, vite=59902)
    assert proc.returncode != 0
    out = proc.stdout + proc.stderr
    assert "8000" not in out or "59901" in out
    assert "未" in out or "FAIL" in out or "没有" in out or "未在" in out
    assert "59901" in out
    assert "59902" in out


def test_backend_listen_vite_down_fails() -> None:
    for _sock, port in _listen():
        proc = _run(backend=port, vite=59903)
        assert proc.returncode != 0
        out = proc.stdout + proc.stderr
        assert str(port) in out
        assert "59903" in out
        assert "LISTEN" in out or "监听" in out
        return
    raise AssertionError("failed to bind test port")


def test_backend_only_with_no_vite_succeeds() -> None:
    for _sock, port in _listen():
        proc = _run("--no-vite", backend=port, vite=59904)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        out = proc.stdout + proc.stderr
        assert str(port) in out
        assert "59904" not in out
        return
    raise AssertionError("failed to bind test port")


def test_both_ports_listening_succeeds() -> None:
    for _backend_sock, backend_port in _listen():
        for _vite_sock, vite_port in _listen():
            proc = _run(backend=backend_port, vite=vite_port)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            out = proc.stdout + proc.stderr
            assert str(backend_port) in out
            assert str(vite_port) in out
            return
    raise AssertionError("failed to bind test ports")
