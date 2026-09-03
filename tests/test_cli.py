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


def test_research_help(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["quantit", "research", "--help"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--strategy" in out
    assert "--promote" in out
    assert "cn_etf_rotation" in out
    assert "hk_quality_book" in out
    assert "cn_quality_book" in out


def test_brief_help(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["quantit", "brief", "--help"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--llm" in out
    assert "not auto-merged" in out.lower()
