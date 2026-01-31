from fastapi import APIRouter, HTTPException

from backend.app.integration_playback.loader import ensure_scenarios_loaded
from backend.app.integration_playback.scenario_registry import list_scenarios
from backend.app.integration_playback.runner import ScenarioRunner

router = APIRouter()


@router.get("/integration_playback/scenarios")
async def get_playback_scenarios():
    """List all registered playback scenarios (backend-driven).

    Scenarios are auto-registered by importing tests/backend/integration/scenario_*.py
    modules. Each scenario exposes metadata for UI menus.
    """
    ensure_scenarios_loaded()
    scenarios = list_scenarios().values()
    return {"scenarios": [s.to_dict() for s in scenarios]}


@router.post("/integration_playback/run")
async def run_playback(body: dict):
    scenario_id = (body or {}).get("scenario_id")
    if not scenario_id:
        raise HTTPException(status_code=400, detail="scenario_id is required")

    ensure_scenarios_loaded()

    runner = ScenarioRunner()
    try:
        result = runner.run(scenario_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
    except Exception as exc:
        # Include partial log so UI can show where it failed.
        return {
            "status": "error",
            "error": repr(exc),
            "log": runner.log,
        }

    return {
        "status": "ok",
        "log": runner.log,
        "result": result,
    }
