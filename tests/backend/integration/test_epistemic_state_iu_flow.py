import pytest

from backend.app.integration_playback.runner import run_scenario
import tests.backend.integration.scenario_epistemic_iu  # registers scenario


@pytest.mark.integration
def test_epistemic_state_tracks_iu_case_without_api():
    # Execute the scenario; assertions live in the scenario steps.
    run_scenario("epistemic_iu_flow")
