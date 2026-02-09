import json
from pathlib import Path
from typing import Dict, List

from backend.app.integration_playback.scenario import Scenario

SCENARIOS: Dict[str, Scenario] = {}


def register_scenario(scenario: Scenario) -> None:
    SCENARIOS[scenario.id] = scenario


def get_scenario(scenario_id: str) -> Scenario:
    if scenario_id not in SCENARIOS:
        raise KeyError(f"Scenario not found: {scenario_id}")
    return SCENARIOS[scenario_id]


def list_scenarios() -> Dict[str, Scenario]:
    return dict(SCENARIOS)


def build_scenario_index() -> List[dict]:
    """Return a deterministic list of scenario dicts for export/UI consumption."""
    return [SCENARIOS[k].to_dict() for k in sorted(SCENARIOS.keys())]


def export_scenarios_json(out_path: str | Path) -> Path:
    """Write the scenario index to JSON for UI/playback clients."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"scenarios": build_scenario_index()}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return path
