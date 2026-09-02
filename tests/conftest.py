import pytest

from quantit.research.params import clear_params_cache


@pytest.fixture(autouse=True)
def _isolate_promoted_params(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTIT_ACTIVE_PARAMS", str(tmp_path / "active_params.yaml"))
    monkeypatch.setenv("QUANTIT_RESEARCH_DIR", str(tmp_path / "research"))
    clear_params_cache()
    yield
    clear_params_cache()
