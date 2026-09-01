"""CLI smoke tests."""

from __future__ import annotations

import pytest

from quantit.cli import main


def test_serve_help(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["quantit", "serve", "--help"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--port" in out
    assert "paper trading" in out.lower() or "serve" in out.lower()
