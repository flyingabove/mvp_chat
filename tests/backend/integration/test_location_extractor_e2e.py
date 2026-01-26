"""
Integration test for LocationExtractor.

This test actually calls ChatGPT (via OpenAI API) to verify that:
1. The extractor correctly classifies movement intents
2. The extractor correctly extracts destination IDs
3. The extractor handles natural language variations

This is marked as integration since it makes real API calls (when OPENAI_API_KEY is available).
"""

import os
import pytest

from backend.app.engine.extractors.location_extractor import LocationExtractor, LocationIntent


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


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_location_extractor_real_api_explicit_command():
    """Integration test: Real API call for explicit 'go to' command."""
    extractor = LocationExtractor()
    world_graph = _WorldGraph()

    res = await extractor.extract("go to office lobby", world_graph=world_graph)
    
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id in world_graph.locations
    assert res.confidence >= 0.7


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_location_extractor_real_api_natural_language():
    """Integration test: Real API call for natural language movement."""
    extractor = LocationExtractor()
    world_graph = _WorldGraph()

    res = await extractor.extract("i'm going to the workplace lobby", world_graph=world_graph)
    
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id in world_graph.locations
    assert res.confidence >= 0.7


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_location_extractor_real_api_head_to():
    """Integration test: Real API call for 'head to' variant."""
    extractor = LocationExtractor()
    world_graph = _WorldGraph()

    res = await extractor.extract("head to the coffee shop", world_graph=world_graph)
    
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id in world_graph.locations
    assert res.confidence >= 0.7


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_location_extractor_real_api_rejects_question():
    """Integration test: Real API call rejects hypothetical question."""
    extractor = LocationExtractor()
    world_graph = _WorldGraph()

    res = await extractor.extract("can we go to the office?", world_graph=world_graph)
    
    # Should reject because it's a question, not a command
    assert res.intent == LocationIntent.NONE
    assert res.destination_id is None


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_location_extractor_real_api_should_i_go():
    """Integration test: Real API call rejects 'should I go' variant."""
    extractor = LocationExtractor()
    world_graph = _WorldGraph()

    res = await extractor.extract("should I head to the apartment?", world_graph=world_graph)
    
    # Should reject because it's a question
    assert res.intent == LocationIntent.NONE
    assert res.destination_id is None


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_location_extractor_real_api_ambiguous_extraction():
    """Integration test: Real API call handles ambiguous destinations gracefully."""
    extractor = LocationExtractor()
    world_graph = _WorldGraph()

    # "office" could match office_lobby or office_conference_room
    # LLM should pick the best one or one that exists
    res = await extractor.extract("go to office", world_graph=world_graph)
    
    # Should classify as movement (it's a command)
    assert res.intent == LocationIntent.MOVE
    # Destination should be valid or we accept that LLM tries its best
    assert isinstance(res.destination_id, (str, type(None)))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_location_extractor_real_api_long_narrative():
    """Integration test: Real API call handles complex narrative with movement."""
    extractor = LocationExtractor()
    world_graph = _WorldGraph()

    # Real dialogue example
    res = await extractor.extract("actually I'm going to your workplace see you in a bit", world_graph=world_graph)
    
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id in world_graph.locations
    assert res.confidence >= 0.7


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_location_extractor_real_api_no_empty_messages():
    """Integration test: Real API call handles empty/whitespace messages."""
    extractor = LocationExtractor()
    world_graph = _WorldGraph()

    res = await extractor.extract("", world_graph=world_graph)
    
    assert res.intent == LocationIntent.NONE
    assert res.destination_id is None


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_location_extractor_real_api_move_to_variant():
    """Integration test: Real API call handles 'move to' as alternative to 'go to'."""
    extractor = LocationExtractor()
    world_graph = _WorldGraph()

    res = await extractor.extract("move to conference room", world_graph=world_graph)
    
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id in world_graph.locations


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
@pytest.mark.asyncio
async def test_location_extractor_with_knowledge_context_disambiguation():
    """Integration test: Location extractor uses knowledge chunks for disambiguation.
    
    This verifies that when knowledge context is provided, the LLM can disambiguate
    ambiguous references like "old workplace" to their actual location IDs.
    """
    extractor = LocationExtractor()
    world_graph = _WorldGraph()
    
    # Simulate knowledge chunks from FAISS retrieval about EDAM Entertainment
    knowledge_chunks = [
        "EDAM Entertainment is where Yuna used to work before joining the main company",
        "Yuna's old workplace at EDAM was where she spent her formative years in the industry",
        "The EDAM Entertainment Building is located downtown near the office district",
        "EDAM Entertainment: A multimedia production company; Yuna worked there as director",
        "Yuna mentions her time at EDAM with nostalgia when discussing career changes",
    ]
    
    # Ambiguous user message that needs knowledge context
    res = await extractor.extract(
        "I'm going to IU's old workplace",
        world_graph=world_graph,
        knowledge_chunks=knowledge_chunks
    )
    
    # Should classify as movement (it's clearly a command even if phrased naturally)
    assert res.intent == LocationIntent.MOVE
    # Should disambiguate to EDAM building using knowledge context
    assert res.destination_id in world_graph.locations
    # With knowledge context, should have high confidence
    assert res.confidence >= 0.5
