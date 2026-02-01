"""Integration playback wrapper for LocationExtractor via OpenAI."""

import pytest

from backend.app.integration_playback.loader import ensure_scenarios_loaded
from backend.app.integration_playback.runner import run_scenario


@pytest.mark.integration
def test_location_extractor_playback(require_openai_api_key):
    ensure_scenarios_loaded()
    result = run_scenario("location_extractor_llm")

    assert all(entry["status"] == "ok" for entry in result["log"])
