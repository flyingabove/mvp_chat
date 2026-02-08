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

        # Class-based scenarios use a dedicated execution path.
        if scenario._scenario_class is not None:
            return await self._run_class_scenario(scenario)

        return await self._run_legacy_scenario(scenario)

    # ------------------------------------------------------------------
    # Class-based execution (IntegrationScenario subclasses)
    # ------------------------------------------------------------------

    async def _run_class_scenario(self, scenario) -> Any:
        cls = scenario._scenario_class
        instance = cls()
        result = None
        idx = 0

        # --- setup ---
        entry = {
            "index": idx,
            "kind": "action",
            "description": "Setup",
            "uses_llm": False,
            "status": "pending",
        }
        try:
            setup_result = instance.setup()
            if asyncio.iscoroutine(setup_result):
                setup_result = await setup_result
            entry["status"] = "ok"
            if setup_result is not None:
                entry["output"] = _strip_state(setup_result)
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = repr(exc)
            self.log.append(entry)
            raise
        self.log.append(entry)

        # --- steps (with cleanup in finally) ---
        step_descs = cls.get_steps()
        try:
            for sd in step_descs:
                idx += 1
                instance._step_index = idx
                entry = {
                    "index": idx,
                    "kind": sd.kind,
                    "description": sd.description,
                    "uses_llm": sd.uses_llm,
                    "status": "pending",
                }
                method = getattr(instance, sd.method_name)
                try:
                    fn_result = method()
                    if asyncio.iscoroutine(fn_result):
                        fn_result = await fn_result
                    result = fn_result
                    entry["status"] = "ok"
                    if fn_result is not None:
                        entry["output"] = _strip_state(fn_result)
                except Exception as exc:
                    entry["status"] = "error"
                    entry["error"] = repr(exc)
                    self.log.append(entry)
                    raise
                self.log.append(entry)
        finally:
            # Cleanup always runs.
            idx += 1
            cleanup_entry = {
                "index": idx,
                "kind": "action",
                "description": "Cleanup",
                "uses_llm": False,
                "status": "pending",
            }
            try:
                cleanup_result = instance.cleanup()
                if asyncio.iscoroutine(cleanup_result):
                    cleanup_result = await cleanup_result
                cleanup_entry["status"] = "ok"
            except Exception as exc:
                cleanup_entry["status"] = "error"
                cleanup_entry["error"] = repr(exc)
            self.log.append(cleanup_entry)

        self.last_result = result
        return result

    # ------------------------------------------------------------------
    # Legacy execution (loose-function Step lists)
    # ------------------------------------------------------------------

    async def _run_legacy_scenario(self, scenario) -> Any:
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
                    state_obj = None
                    if isinstance(fn_result, dict) and "state" in fn_result:
                        state_obj = fn_result.get("state")
                    elif fn_result is not None:
                        state_obj = fn_result
                    if state_obj is not None:
                        self.context.setdefault("state", state_obj)

                entry["status"] = "ok"

                if fn_result is not None:
                    log_output = _strip_state(fn_result)
                    if log_output is not None:
                        entry["output"] = log_output
            except Exception as exc:
                entry["status"] = "error"
                entry["error"] = repr(exc)
                self.log.append(entry)
                raise

            self.log.append(entry)

        self.last_result = result
        return result


def _strip_state(fn_result: Any) -> Any:
    """Remove heavy state objects from log output."""
    if isinstance(fn_result, dict) and "state" in fn_result:
        out = {k: v for k, v in fn_result.items() if k != "state"}
        return out or None
    return fn_result


def run_scenario(scenario_id: str):
    runner = ScenarioRunner()
    # In test/CLI contexts there may be no running loop; use asyncio.run.
    result = asyncio.run(runner.run_async(scenario_id))
    return {"result": result, "log": runner.log}


async def run_scenario_async(scenario_id: str):
    runner = ScenarioRunner()
    result = await runner.run_async(scenario_id)
    return {"result": result, "log": runner.log}
