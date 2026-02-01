import pytest

from backend.app.integration_playback.loader import ensure_scenarios_loaded
from backend.app.integration_playback.runner import run_scenario


@pytest.mark.integration
def test_api_end_to_end_5_turns_time_and_location():
    ensure_scenarios_loaded()
    result = run_scenario("api_chat_5_turns_time_location")

    log = result["log"]
    assert all(entry["status"] == "ok" for entry in log), "Scenario steps did not all succeed"
