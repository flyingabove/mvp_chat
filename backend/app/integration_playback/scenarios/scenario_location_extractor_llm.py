from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.app.config.credentials import get_openai_api_key
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
    title = "Location extractor live checks"
    description = "Runs LocationExtractor against OpenAI for realistic movement phrasing."
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
        if not get_openai_api_key():
            raise RuntimeError("OPENAI_API_KEY is required for playback")
        return {"reply": "*Spinning up LocationExtractor scenario.*", **self.debug_info()}

    async def _extract_expect_move(self, message: str, min_conf: float = 0.7):
        res = await self.state.extractor.extract(message, world_graph=self.state.world_graph)
        self.state.last_result = res
        assert res.intent == LocationIntent.MOVE
        assert res.destination_id in self.state.world_graph.locations
        assert res.confidence >= min_conf
        return self.debug_info({"intent": res.intent.value, "destination_id": res.destination_id, "confidence": res.confidence})

    async def _extract_expect_none(self, message: str):
        res = await self.state.extractor.extract(message, world_graph=self.state.world_graph)
        self.state.last_result = res
        assert res.intent == LocationIntent.NONE
        assert res.destination_id is None
        return self.debug_info({"intent": res.intent.value, "destination_id": res.destination_id, "confidence": res.confidence})

    async def _extract_ambiguous(self, message: str):
        res = await self.state.extractor.extract(message, world_graph=self.state.world_graph)
        self.state.last_result = res
        assert res.intent == LocationIntent.MOVE
        return self.debug_info({"intent": res.intent.value, "destination_id": res.destination_id, "confidence": res.confidence})

    async def _extract_with_knowledge(self, message: str):
        res = await self.state.extractor.extract(message, world_graph=self.state.world_graph, knowledge_chunks=self.state.knowledge_chunks)
        self.state.last_result = res
        assert res.intent == LocationIntent.MOVE
        assert res.destination_id in self.state.world_graph.locations
        assert res.confidence >= 0.5
        return self.debug_info({"intent": res.intent.value, "destination_id": res.destination_id, "confidence": res.confidence, "knowledge_used": True})

    @step(kind="assert", description="Explicit go-to", uses_llm=True)
    async def explicit_go_to(self):
        return await self._extract_expect_move("go to office lobby", 0.7)

    @step(kind="assert", description="Natural language", uses_llm=True)
    async def natural_language(self):
        return await self._extract_expect_move("i'm going to the workplace lobby", 0.7)

    @step(kind="assert", description="head-to", uses_llm=True)
    async def head_to_variant(self):
        return await self._extract_expect_move("head to the coffee shop", 0.7)

    @step(kind="assert", description="Reject question", uses_llm=True)
    async def reject_question(self):
        return await self._extract_expect_none("can we go to the office?")

    @step(kind="assert", description="Reject should-I", uses_llm=True)
    async def reject_should_i(self):
        return await self._extract_expect_none("should I head to the apartment?")

    @step(kind="assert", description="Ambiguous extraction", uses_llm=True)
    async def ambiguous(self):
        return await self._extract_ambiguous("go to office")

    @step(kind="assert", description="Long narrative", uses_llm=True)
    async def long_narrative(self):
        return await self._extract_expect_move("actually I'm going to your workplace see you in a bit", 0.7)

    @step(kind="assert", description="Whitespace input", uses_llm=True)
    async def empty_input(self):
        return await self._extract_expect_none("")

    @step(kind="assert", description="move-to variant", uses_llm=True)
    async def move_to_variant(self):
        return await self._extract_expect_move("move to conference room", 0.0)

    @step(kind="assert", description="Knowledge disambiguation", uses_llm=True)
    async def disambiguate_with_knowledge(self):
        return await self._extract_with_knowledge("I'm going to IU's old workplace")
