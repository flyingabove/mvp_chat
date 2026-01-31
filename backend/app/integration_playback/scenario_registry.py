from typing import Dict

from backend.app.integration_playback.scenario import Scenario, Step

SCENARIOS: Dict[str, Scenario] = {}


def register_scenario(scenario: Scenario) -> None:
    SCENARIOS[scenario.id] = scenario


def get_scenario(scenario_id: str) -> Scenario:
    if scenario_id not in SCENARIOS:
        raise KeyError(f"Scenario not found: {scenario_id}")
    return SCENARIOS[scenario_id]


def list_scenarios() -> Dict[str, Scenario]:
    return dict(SCENARIOS)
