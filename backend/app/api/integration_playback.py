from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.dependencies import require_operator
from backend.app.integration_playback.loader import ensure_scenarios_loaded
from backend.app.integration_playback.scenario_registry import list_scenarios
from backend.app.integration_playback.runner import ScenarioRunner

# A03: playback runs real turns through the model pipeline and can read
# other scenarios' logs — operator-only, disabled by default in prod-like
# environments (see require_operator / DEBUG_TOOLS_ENABLED).
router = APIRouter(dependencies=[Depends(require_operator)])


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
        result = await runner.run_async(scenario_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
    except Exception as exc:
        return {"status": "error", "error": repr(exc), "log": runner.log}

    return {"status": "ok", "log": runner.log, "result": result}
