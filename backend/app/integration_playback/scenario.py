from __future__ import annotations

import datetime
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Dict, List, Optional, Type


# ---------------------------------------------------------------------------
# Legacy Step / Scenario dataclasses (kept for backward compat + registry)
# ---------------------------------------------------------------------------

@dataclass
class Step:
    kind: str  # e.g., "action", "assert", "note"
    description: str
    fn: Optional[Callable[..., Any]] = None
    kwargs: Dict[str, Any] = field(default_factory=dict)
    uses_llm: bool = False  # flag so UI can label LLM-backed steps
    mode: str = ""  # e.g., cached|live for llm/extractor steps
    payload: Dict[str, Any] = field(default_factory=dict)  # authored data for user/system/llm steps
    cached_response: Any = None  # optional deterministic output for cached llm/extractor

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "description": self.description,
            "has_fn": self.fn is not None,
            "kwargs": self.kwargs,
            "uses_llm": self.uses_llm,
            "mode": self.mode,
            "payload": self.payload,
            "cached_response": self.cached_response,
        }


@dataclass
class Scenario:
    id: str
    title: str
    description: str
    tags: List[str]
    requires_api_key: bool = False
    requires_cache: bool = False
    steps: List[Step] = field(default_factory=list)
    _scenario_class: Optional[Type["IntegrationScenario"]] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "requires_api_key": self.requires_api_key,
            "requires_cache": self.requires_cache,
            "steps": [s.to_dict() for s in self.steps],
        }


# ---------------------------------------------------------------------------
# @step decorator
# ---------------------------------------------------------------------------

_step_counter = 0


def step(kind: str = "action", description: str = "", uses_llm: bool = False, order: int | None = None):
    """Mark a method as a scenario step.  Decorated methods are collected by
    ``IntegrationScenario.get_steps()`` in *order* order."""
    global _step_counter
    _step_counter += 1
    auto_order = _step_counter

    def decorator(fn: Callable) -> Callable:
        fn._step_meta = {
            "kind": kind,
            "description": description or fn.__name__.replace("_", " ").strip(),
            "uses_llm": uses_llm,
            "order": order if order is not None else auto_order,
        }
        return fn

    return decorator


# ---------------------------------------------------------------------------
# StepDescriptor – lightweight description of a class-based step
# ---------------------------------------------------------------------------

@dataclass
class StepDescriptor:
    method_name: str
    kind: str
    description: str
    uses_llm: bool = False


# ---------------------------------------------------------------------------
# IntegrationScenario base class
# ---------------------------------------------------------------------------

class IntegrationScenario(ABC):
    """Universal base class for integration test scenarios.

    Subclasses define metadata as class variables and steps as ``@step``
    decorated methods.  Registration happens automatically on class creation
    via ``__init_subclass__``.
    """

    # -- Class-level metadata (override in subclasses) --
    scenario_id: ClassVar[str] = ""
    title: ClassVar[str] = ""
    description: ClassVar[str] = ""
    tags: ClassVar[List[str]] = []
    requires_api_key: ClassVar[bool] = False
    requires_cache: ClassVar[bool] = False
    player_role: ClassVar[str] = ""  # speaker name that represents the user/player (e.g. "Detective")

    def __init__(self) -> None:
        self.state: Any = None
        self._step_index: int = 0

    # -- Env helpers --
    @staticmethod
    def _ensure_openai_api_key() -> str | None:
        """Return OPENAI_API_KEY using centralized credential loading."""
        from backend.app.config.credentials import get_openai_api_key
        return get_openai_api_key() or None

    # -- Auto-registration on subclass creation --
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "scenario_id", ""):
            return
        from backend.app.integration_playback.scenario_registry import register_scenario

        register_scenario(_build_scenario_from_class(cls))

    # -- Lifecycle hooks (override as needed) --
    def setup(self) -> Any:
        """Called before the first step.  Return a dict for playback output."""
        return None

    def cleanup(self) -> Any:
        """Called after all steps (including on failure)."""
        return None

    # -- Step collection --
    @classmethod
    def get_steps(cls) -> List[StepDescriptor]:
        """Collect ``@step``-decorated methods in declaration order."""
        methods: list[tuple[int, str, dict]] = []
        for name in dir(cls):
            attr = getattr(cls, name, None)
            if callable(attr) and hasattr(attr, "_step_meta"):
                meta = attr._step_meta
                methods.append((meta["order"], name, meta))
        methods.sort(key=lambda x: x[0])
        return [
            StepDescriptor(
                method_name=name,
                kind=meta["kind"],
                description=meta["description"],
                uses_llm=meta.get("uses_llm", False),
            )
            for _, name, meta in methods
        ]

    # -- Pytest entry point --
    @classmethod
    def run_as_test(cls) -> None:
        """Run this scenario through the playback runner and assert all steps pass."""
        from backend.app.integration_playback.runner import run_scenario

        # Ensure API key presence (prefers env var, falls back to .env.test when available)
        cls._ensure_openai_api_key()

        result = run_scenario(cls.scenario_id)
        log = result["log"]
        assert all(entry["status"] == "ok" for entry in log), (
            "Scenario steps did not all succeed: "
            + ", ".join(f"{e['description']}={e['status']}" for e in log if e["status"] != "ok")
        )

    # -- Debug helper --
    def debug_info(self, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Build a standardized debug payload rendered as a bordered box."""
        info: Dict[str, Any] = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p"),
            "scenario": self.scenario_id,
            "step": self._step_index,
        }
        if self.state is not None:
            for attr in ("location", "location_id", "minute", "story"):
                val = getattr(self.state, attr, None)
                if val is not None:
                    info[attr] = val
            # Surface speakers generically so both game and playback can render the same debug box
            if "speakers" not in info:
                speakers: list[str] = []
                if self.player_role:
                    speakers.append(self.player_role)
                beliefs = getattr(self.state, "beliefs", None)
                if isinstance(beliefs, dict):
                    speakers.extend(str(k) for k in beliefs.keys())
                if speakers:
                    # Preserve insertion order while removing duplicates
                    seen = set()
                    info["speakers"] = [s for s in speakers if not (s in seen or seen.add(s))]
        if extra:
            info.update(extra)
        return {"debug_box": info}

    # -- Chat message helpers (explicitly label user vs LLM) --
    def say_user(self, text: str) -> Dict[str, Any]:
        """Return a chat-style payload tagged as the player/user."""
        speaker = self.player_role or "User"
        return {"user": speaker, "reply": text, "role": "user"}

    def say_llm(self, speaker: str, text: str) -> Dict[str, Any]:
        """Return a chat-style payload tagged as LLM/system."""
        return {"user": speaker, "reply": text, "role": "llm"}

    def say_system(self, text: str) -> Dict[str, Any]:
        """Return a chat-style payload tagged as system/LLM narrator."""
        return {"user": "System", "reply": text, "role": "llm"}


# ---------------------------------------------------------------------------
# Bridge: class -> legacy Scenario dataclass
# ---------------------------------------------------------------------------

def _build_scenario_from_class(cls: Type[IntegrationScenario]) -> Scenario:
    step_descs = cls.get_steps()
    legacy_steps: list[Step] = []
    for sd in step_descs:
        legacy_steps.append(
            Step(kind=sd.kind, description=sd.description, uses_llm=sd.uses_llm)
        )
    return Scenario(
        id=cls.scenario_id,
        title=cls.title,
        description=cls.description,
        tags=list(cls.tags),
        requires_api_key=cls.requires_api_key,
        requires_cache=cls.requires_cache,
        steps=legacy_steps,
        _scenario_class=cls,
    )
