from typing import Any

from backend.app.integration_playback.scenario_registry import get_scenario


class ScenarioRunner:
    def __init__(self):
        self.last_result: Any = None
        self.context: dict[str, Any] = {}
        self.log: list[dict[str, Any]] = []

    def run(self, scenario_id: str) -> Any:
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

            # Notes still appear in the log so the UI can display them.
            if step.kind == "note" or step.fn is None:
                entry["status"] = "skipped"
                self.log.append(entry)
                continue

            call_kwargs = dict(step.kwargs)
            for k, v in call_kwargs.items():
                if v is None and k in self.context:
                    call_kwargs[k] = self.context[k]

            try:
                if step.kind == "action":
                    result = step.fn(**call_kwargs)
                    if result is not None:
                        # If the action returns a state, store it for later steps.
                        self.context.setdefault("state", result)
                elif step.kind == "assert":
                    step.fn(**call_kwargs)
                else:
                    step.fn(**call_kwargs)
                entry["status"] = "ok"
            except Exception as exc:  # surfacing traceback to caller
                entry["status"] = "error"
                entry["error"] = repr(exc)
                self.log.append(entry)
                raise
            self.log.append(entry)
        self.last_result = result
        return result


def run_scenario(scenario_id: str):
    runner = ScenarioRunner()
    result = runner.run(scenario_id)
    return {"result": result, "log": runner.log}
