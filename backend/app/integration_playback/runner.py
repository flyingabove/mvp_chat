import asyncio
from typing import Any

from backend.app.integration_playback.scenario_registry import get_scenario


class ScenarioRunner:
    def __init__(self):
        self.last_result: Any = None
        self.context: dict[str, Any] = {}
        self.log: list[dict[str, Any]] = []

    async def run_async(self, scenario_id: str) -> Any:
        scenario = get_scenario(scenario_id)
        result = None
        for idx, step in enumerate(scenario.steps):
            entry = {
                "index": idx,
                "kind": step.kind,
                "description": step.description,
                "uses_llm": getattr(step, "uses_llm", False),
                "status": "pending",
            }

            if step.kind == "note" or step.fn is None:
                entry["status"] = "skipped"
                self.log.append(entry)
                continue

            call_kwargs = dict(step.kwargs)
            for k, v in call_kwargs.items():
                if v is None and k in self.context:
                    call_kwargs[k] = self.context[k]

            try:
                fn_result = step.fn(**call_kwargs)
                if asyncio.iscoroutine(fn_result):
                    fn_result = await fn_result

                if step.kind == "action":
                    result = fn_result
                    if result is not None:
                        self.context.setdefault("state", result)
                entry["status"] = "ok"
                if fn_result is not None:
                    # Capture lightweight output so UI can show dialogue/results.
                    entry["output"] = fn_result
            except Exception as exc:
                entry["status"] = "error"
                entry["error"] = repr(exc)
                self.log.append(entry)
                raise

            self.log.append(entry)

        self.last_result = result
        return result


def run_scenario(scenario_id: str):
    runner = ScenarioRunner()
    # In test/CLI contexts there may be no running loop; use asyncio.run.
    result = asyncio.run(runner.run_async(scenario_id))
    return {"result": result, "log": runner.log}


async def run_scenario_async(scenario_id: str):
    runner = ScenarioRunner()
    result = await runner.run_async(scenario_id)
    return {"result": result, "log": runner.log}
