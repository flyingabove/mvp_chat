import pytest

from backend.app.integration_playback.loader import ensure_scenarios_loaded
from backend.app.integration_playback.runner import run_scenario


@pytest.mark.integration
def test_character_retrieval_returns_real_knowledge():
    ensure_scenarios_loaded()
    result = run_scenario("character_retrieval_e2e")

    assert all(entry["status"] == "ok" for entry in result["log"])
