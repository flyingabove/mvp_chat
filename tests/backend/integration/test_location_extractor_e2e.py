"""Playback scenario for LocationExtractor real OpenAI calls."""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.app.engine.extractors.location_extractor import LocationExtractor, LocationIntent
from backend.app.integration_playback.scenario import IntegrationScenario, step


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


class LocationExtractorScenario(IntegrationScenario):
    scenario_id = "location_extractor_llm"
    title = "Location extractor: realistic phrasing against OpenAI"
    description = (
        "Runs the LocationExtractor against real OpenAI for a variety of human-sounding movement phrases, including "
        "a knowledge-guided disambiguation. The assertions are unchanged; only the narration is more natural."
    )
    tags = ["integration", "extractor", "llm"]
    requires_api_key = True
    player_role = "Player"

    def setup(self):
        ctx = LocationExtractorContext()
        ctx.knowledge_chunks = [
            {"text": "EDAM Entertainment is where IU used to work before joining the main company"},
            {"text": "IU's old workplace at EDAM was where she spent her formative years in the industry"},
            {"text": "The EDAM Entertainment Building is located downtown near the office district"},
            {"text": "EDAM Entertainment: A multimedia production company; IU worked there as director"},
            {"text": "IU mentions her time at EDAM with nostalgia when discussing career changes"},
        ]
        self.state = ctx
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for playback")
        return {
            "reply": "*Spinning up the LocationExtractor with a small, easy-to-reason-about world graph.*",
            **self.debug_info(),
        }

    # -- Helper methods (not steps) --

    async def _extract_expect_move(self, message: str, min_conf: float = 0.7):
        res = await self.state.extractor.extract(message, world_graph=self.state.world_graph)
        self.state.last_result = res
        assert res.intent == LocationIntent.MOVE
        assert res.destination_id in self.state.world_graph.locations
        assert res.confidence >= min_conf
        return [
            self.say_user(message),
            self.say_llm("Extractor", f"*Move detected -> {res.destination_id}.* Confidence: {res.confidence:.2f}."),
            self.debug_info({"intent": res.intent.value, "destination_id": res.destination_id, "confidence": res.confidence}),
        ]

    async def _extract_expect_none(self, message: str):
        res = await self.state.extractor.extract(message, world_graph=self.state.world_graph)
        self.state.last_result = res
        assert res.intent == LocationIntent.NONE
        assert res.destination_id is None
        display_msg = message if message.strip() else "(empty)"
        return [
            self.say_user(display_msg),
            self.say_llm("Extractor", "*No movement intent detectedtreating as conversation.*"),
            self.debug_info({"intent": res.intent.value, "destination_id": res.destination_id, "confidence": res.confidence}),
        ]

    async def _extract_ambiguous(self, message: str):
        res = await self.state.extractor.extract(message, world_graph=self.state.world_graph)
        self.state.last_result = res
        assert res.intent == LocationIntent.MOVE
        assert isinstance(res.destination_id, (str, type(None)))
        return [
            self.say_user(message),
            self.say_llm("Extractor", f"*Movement intent detected, destination ambiguous:* \"{res.destination_id or 'unknown'}\" (conf {res.confidence:.2f})."),
            self.debug_info({"intent": res.intent.value, "destination_id": res.destination_id, "confidence": res.confidence}),
        ]

    async def _extract_with_knowledge(self, message: str):
        res = await self.state.extractor.extract(
            message,
            world_graph=self.state.world_graph,
            knowledge_chunks=self.state.knowledge_chunks,
        )
        self.state.last_result = res
        assert res.intent == LocationIntent.MOVE
        assert res.destination_id in self.state.world_graph.locations
        assert res.confidence >= 0.5
        return [
            self.say_user(message),
            self.say_llm("Extractor", f"*Knowledge-guided routing -> {res.destination_id}.* Confidence: {res.confidence:.2f}."),
            self.debug_info({"intent": res.intent.value, "destination_id": res.destination_id, "confidence": res.confidence, "knowledge_used": True}),
        ]

    # -- Steps --

    @step(kind="assert", description="Explicit 'go to' command", uses_llm=True)
    async def explicit_go_to(self):
        return await self._extract_expect_move("go to office lobby", 0.7)

    @step(kind="assert", description="Natural language movement", uses_llm=True)
    async def natural_language(self):
        return await self._extract_expect_move("i'm going to the workplace lobby", 0.7)

    @step(kind="assert", description="'head to' variant", uses_llm=True)
    async def head_to_variant(self):
        return await self._extract_expect_move("head to the coffee shop", 0.7)

    @step(kind="assert", description="Reject question", uses_llm=True)
    async def reject_question(self):
        return await self._extract_expect_none("can we go to the office?")

    @step(kind="assert", description="Reject 'should I go'", uses_llm=True)
    async def reject_should_i(self):
        return await self._extract_expect_none("should I head to the apartment?")

    @step(kind="assert", description="Ambiguous extraction", uses_llm=True)
    async def ambiguous(self):
        return await self._extract_ambiguous("go to office")

    @step(kind="assert", description="Long narrative movement", uses_llm=True)
    async def long_narrative(self):
        return await self._extract_expect_move("actually I'm going to your workplace see you in a bit", 0.7)

    @step(kind="assert", description="Handle empty/whitespace", uses_llm=True)
    async def empty_input(self):
        return await self._extract_expect_none("")

    @step(kind="assert", description="'move to' variant", uses_llm=True)
    async def move_to_variant(self):
        return await self._extract_expect_move("move to conference room", 0.0)

    @step(kind="assert", description="Disambiguate with knowledge", uses_llm=True)
    async def disambiguate_with_knowledge(self):
        return await self._extract_with_knowledge("I'm going to IU's old workplace")


# -- Pytest entry point --
import pytest  # noqa: E402

@pytest.mark.integration
def test_location_extractor_playback(require_openai_api_key):
    LocationExtractorScenario.run_as_test()
