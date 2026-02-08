"""Playback scenario for LocationExtractor real OpenAI calls."""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.app.engine.extractors.location_extractor import LocationExtractor, LocationIntent
from backend.app.integration_playback.scenario import Scenario, Step
from backend.app.integration_playback.scenario_registry import register_scenario


class _Loc:
    def __init__(self, name: str, id: str = ""):
        self.name = name
        self.id = id


class _WorldGraph:
    def __init__(self):
        self.locations = {
            "office_lobby": _Loc("Office Lobby", "office_lobby"),
            "office_conference_room": _Loc("Conference Room", "office_conference_room"),
            "coffee_shop": _Loc("Coffee Shop", "coffee_shop"),
            "apartment": _Loc("Apartment", "apartment"),
            "apartment_bedroom": _Loc("Bedroom", "apartment_bedroom"),
            "workplace_lobby": _Loc("Workplace Lobby", "workplace_lobby"),
            "edam_building": _Loc("EDAM Entertainment Building", "edam_building"),
        }


@dataclass
class LocationExtractorContext:
    extractor: LocationExtractor = field(default_factory=LocationExtractor)
    world_graph: _WorldGraph = field(default_factory=_WorldGraph)
    knowledge_chunks: List[Dict[str, str]] = field(default_factory=list)
    last_result: Any = None


def _init_context() -> LocationExtractorContext:
    ctx = LocationExtractorContext()
    ctx.knowledge_chunks = [
        {"text": "EDAM Entertainment is where IU used to work before joining the main company"},
        {"text": "IU's old workplace at EDAM was where she spent her formative years in the industry"},
        {"text": "The EDAM Entertainment Building is located downtown near the office district"},
        {"text": "EDAM Entertainment: A multimedia production company; IU worked there as director"},
        {"text": "IU mentions her time at EDAM with nostalgia when discussing career changes"},
    ]
    return {
        "state": ctx,
        "reply": "Spinning up the LocationExtractor with a small, easy-to-reason-about world graph.",
    }


def _ensure_api_key(state: LocationExtractorContext):
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for playback")


async def _extract_expect_move(state: LocationExtractorContext, message: str, min_conf: float = 0.7):
    res = await state.extractor.extract(message, world_graph=state.world_graph)
    state.last_result = res
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id in state.world_graph.locations
    assert res.confidence >= min_conf
    return [
        {
            "user": "Player",
            "reply": message,
            "debug": {
                "message": message,
                "intent": res.intent.value,
                "destination_id": res.destination_id,
                "confidence": res.confidence,
            },
        },
        {
            "user": "Extractor",
            "reply": f"Got it—I'll treat that as a move to {res.destination_id} (conf {res.confidence:.2f}).",
        },
    ]


async def _extract_expect_none(state: LocationExtractorContext, message: str):
    res = await state.extractor.extract(message, world_graph=state.world_graph)
    state.last_result = res
    assert res.intent == LocationIntent.NONE
    assert res.destination_id is None
    return [
        {
            "user": "Player",
            "reply": message,
            "debug": {
                "message": message,
                "intent": res.intent.value,
                "destination_id": res.destination_id,
                "confidence": res.confidence,
            },
        },
        {
            "user": "Extractor",
            "reply": "Sounds like conversation (not travel)—no movement intent detected.",
        },
    ]


async def _extract_ambiguous(state: LocationExtractorContext, message: str):
    res = await state.extractor.extract(message, world_graph=state.world_graph)
    state.last_result = res
    assert res.intent == LocationIntent.MOVE
    assert isinstance(res.destination_id, (str, type(None)))
    return [
        {
            "user": "Player",
            "reply": message,
            "debug": {
                "message": message,
                "intent": res.intent.value,
                "destination_id": res.destination_id,
                "confidence": res.confidence,
            },
        },
        {
            "user": "Extractor",
            "reply": (
                f"I think you want to move, but the destination is ambiguous: {res.destination_id or 'unknown'} "
                f"(conf {res.confidence:.2f})."
            ),
        },
    ]


async def _extract_with_knowledge(state: LocationExtractorContext, message: str):
    res = await state.extractor.extract(
        message,
        world_graph=state.world_graph,
        knowledge_chunks=state.knowledge_chunks,
    )
    state.last_result = res
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id in state.world_graph.locations
    assert res.confidence >= 0.5
    return [
        {
            "user": "Player",
            "reply": message,
            "debug": {
                "message": message,
                "intent": res.intent.value,
                "destination_id": res.destination_id,
                "confidence": res.confidence,
                "knowledge_chunks": state.knowledge_chunks,
            },
        },
        {
            "user": "Extractor",
            "reply": f"Using the knowledge hints, I'd route you to {res.destination_id} (conf {res.confidence:.2f}).",
        },
    ]


steps = [
    Step(kind="action", description="Init extractor context", fn=_init_context, uses_llm=False),
    Step(kind="assert", description="Ensure OPENAI_API_KEY present", fn=_ensure_api_key, kwargs={"state": None}, uses_llm=False),
    Step(kind="assert", description="Explicit 'go to' command", fn=_extract_expect_move, kwargs={"state": None, "message": "go to office lobby", "min_conf": 0.7}, uses_llm=True),
    Step(kind="assert", description="Natural language movement", fn=_extract_expect_move, kwargs={"state": None, "message": "i'm going to the workplace lobby", "min_conf": 0.7}, uses_llm=True),
    Step(kind="assert", description="'head to' variant", fn=_extract_expect_move, kwargs={"state": None, "message": "head to the coffee shop", "min_conf": 0.7}, uses_llm=True),
    Step(kind="assert", description="Reject question", fn=_extract_expect_none, kwargs={"state": None, "message": "can we go to the office?"}, uses_llm=True),
    Step(kind="assert", description="Reject 'should I go'", fn=_extract_expect_none, kwargs={"state": None, "message": "should I head to the apartment?"}, uses_llm=True),
    Step(kind="assert", description="Ambiguous extraction", fn=_extract_ambiguous, kwargs={"state": None, "message": "go to office"}, uses_llm=True),
    Step(kind="assert", description="Long narrative movement", fn=_extract_expect_move, kwargs={"state": None, "message": "actually I'm going to your workplace see you in a bit", "min_conf": 0.7}, uses_llm=True),
    Step(kind="assert", description="Handle empty/whitespace", fn=_extract_expect_none, kwargs={"state": None, "message": ""}, uses_llm=True),
    Step(kind="assert", description="'move to' variant", fn=_extract_expect_move, kwargs={"state": None, "message": "move to conference room", "min_conf": 0.0}, uses_llm=True),
    Step(kind="assert", description="Disambiguate with knowledge", fn=_extract_with_knowledge, kwargs={"state": None, "message": "I'm going to IU's old workplace"}, uses_llm=True),
]

SCENARIO_LOCATION_EXTRACTOR = Scenario(
    id="location_extractor_llm",
    title="Location extractor: realistic phrasing against OpenAI",
    description=(
        "Runs the LocationExtractor against real OpenAI for a variety of human-sounding movement phrases, including "
        "a knowledge-guided disambiguation. The assertions are unchanged; only the narration is more natural."
    ),
    tags=["integration", "extractor", "llm"],
    requires_api_key=True,
    requires_cache=False,
    steps=steps,
)

register_scenario(SCENARIO_LOCATION_EXTRACTOR)
