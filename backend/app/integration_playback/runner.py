import asyncio
import json
import sys
from typing import Any

from backend.app.integration_playback.scenario_registry import get_scenario


# ---------------------------------------------------------------------------
# Live output printing — streams step results as they happen
# ---------------------------------------------------------------------------

def _print_live(text: str) -> None:
    """Write text to stdout immediately (handles Windows cp1252 gracefully)."""
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.write(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))
    sys.stdout.flush()


def _format_debug_box(box: dict) -> str:
    """Format a debug_box dict as readable lines."""
    lines = []
    if box.get("timestamp"):
        lines.append(f"  Timestamp:   {box['timestamp']}")
    if box.get("location"):
        lines.append(f"  Location:    {box['location']}")
    if box.get("location_id"):
        lines.append(f"  Location ID: {box['location_id']}")
    if box.get("minute") is not None:
        lines.append(f"  Minute:      {box['minute']}")
    if box.get("story"):
        lines.append(f"  Story:       {box['story']}")
    if box.get("scenario"):
        lines.append(f"  Scenario:    {box['scenario']}")
    skip = {"timestamp", "location", "location_id", "minute", "story", "scenario", "step"}
    for k, v in box.items():
        if k not in skip:
            display = json.dumps(v, default=str) if isinstance(v, (dict, list)) else str(v)
            lines.append(f"  {k}: {display}")
    return "\n".join(lines)


# ANSI color codes
_BLUE = "\033[94m"
_ORANGE = "\033[33m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _emit_output(output: Any, debug: bool = False, player_role: str = "") -> None:
    """Print a step's output to stdout immediately.

    Handles the two shapes returned by steps:
    - Single dict  {"user": ..., "reply": ..., "debug_box": ...}
    - List of dicts [{...}, {...}, ...]

    Messages from ``player_role`` are tagged [USER] in blue.
    All other character messages are tagged [LLM] in orange.
    """
    if output is None:
        return

    items = output if isinstance(output, list) else [output]

    for item in items:
        if not isinstance(item, dict):
            continue

        # Debug box — only show when debug mode requested
        if "debug_box" in item and not item.get("reply"):
            if debug:
                _print_live(f"\n  {_DIM}{'─' * 40}\n  DEBUG INFO\n  {'─' * 40}{_RESET}\n")
                _print_live(_DIM + _format_debug_box(item["debug_box"]) + _RESET + "\n")
                _print_live(f"  {_DIM}{'─' * 40}{_RESET}\n")
            continue

        # Conversational message
        speaker = item.get("user", "")
        reply = item.get("reply", "")
        if not reply:
            continue

        is_user = bool(player_role and speaker == player_role)

        if is_user:
            _print_live(f"\n  {_BLUE}[USER] {speaker}: {reply}{_RESET}\n")
        elif speaker:
            _print_live(f"\n  {_ORANGE}[LLM] {speaker}: {reply}{_RESET}\n")
        else:
            _print_live(f"\n  {reply}\n")

        # Inline debug_box on the same message
        if debug and "debug_box" in item:
            _print_live(f"\n  {_DIM}{'─' * 40}\n  DEBUG INFO\n  {'─' * 40}{_RESET}\n")
            _print_live(_DIM + _format_debug_box(item["debug_box"]) + _RESET + "\n")
            _print_live(f"  {_DIM}{'─' * 40}{_RESET}\n")


class ScenarioRunner:
    def __init__(self, live: bool = True, debug: bool = False):
        self.last_result: Any = None
        self.context: dict[str, Any] = {}
        self.log: list[dict[str, Any]] = []
        self.live = live
        self.debug = debug
        self._player_role: str = ""

    async def run_async(self, scenario_id: str) -> Any:
        scenario = get_scenario(scenario_id)

        # Class-based scenarios use a dedicated execution path.
        if scenario._scenario_class is not None:
            return await self._run_class_scenario(scenario)

        return await self._run_legacy_scenario(scenario)

    def _emit(self, description: str, status: str, output: Any = None) -> None:
        """Print step header + output immediately if live mode is on."""
        if not self.live:
            return
        marker = "+" if status == "ok" else "x" if status == "error" else "."
        _print_live(f"\n  [{marker}] {description}\n")
        if output is not None:
            _emit_output(output, debug=self.debug, player_role=self._player_role)

    # ------------------------------------------------------------------
    # Class-based execution (IntegrationScenario subclasses)
    # ------------------------------------------------------------------

    async def _run_class_scenario(self, scenario) -> Any:
        cls = scenario._scenario_class
        instance = cls()
        result = None
        idx = 0
        self._player_role = getattr(cls, "player_role", "") or ""

        if self.live:
            _print_live(f"\n{'=' * 60}\n  {scenario.title}\n{'=' * 60}\n")

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
            self._emit("Setup", "error")
            raise
        self.log.append(entry)
        self._emit("Setup", "ok", entry.get("output"))

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
                    self._emit(sd.description, "error")
                    raise
                self.log.append(entry)
                self._emit(sd.description, "ok", entry.get("output"))
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

        if self.live:
            _print_live(f"\n{'=' * 60}\n")

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


def run_scenario(scenario_id: str, live: bool = True, debug: bool = False):
    runner = ScenarioRunner(live=live, debug=debug)
    # In test/CLI contexts there may be no running loop; use asyncio.run.
    result = asyncio.run(runner.run_async(scenario_id))
    return {"result": result, "log": runner.log}


async def run_scenario_async(scenario_id: str, live: bool = True, debug: bool = False):
    runner = ScenarioRunner(live=live, debug=debug)
    result = await runner.run_async(scenario_id)
    return {"result": result, "log": runner.log}
