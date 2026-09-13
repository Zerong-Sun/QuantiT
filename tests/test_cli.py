"""CLI smoke tests."""

from __future__ import annotations

import pytest

from quantit.cli import main, maybe_serve_log_config


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


def test_serve_log_config_default_is_console_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTIT_LOG_FILE", raising=False)
    assert maybe_serve_log_config() is None


def test_serve_log_config_rotating_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "runners" / "backend.log"
    monkeypatch.setenv("QUANTIT_LOG_FILE", str(dest))
    monkeypatch.setenv("QUANTIT_LOG_MAX_BYTES", "2048")
    monkeypatch.setenv("QUANTIT_LOG_BACKUPS", "3")
    cfg = maybe_serve_log_config()
    assert cfg is not None
    assert dest.parent.is_dir()
    file_handlers = [
        handler
        for handler in cfg["handlers"].values()
        if handler.get("class") == "logging.handlers.RotatingFileHandler"
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0]["filename"] == str(dest)
    assert file_handlers[0]["maxBytes"] == 2048
    assert file_handlers[0]["backupCount"] == 3
    assert any(handler.get("class") == "logging.StreamHandler" for handler in cfg["handlers"].values())
    assert "console" in cfg["root"]["handlers"]
    assert "file" in cfg["root"]["handlers"]
