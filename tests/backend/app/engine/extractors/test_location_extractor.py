import pytest

from backend.app.engine.extractors.location_extractor import LocationExtractor, LocationIntent, LocationExtraction


class _Loc:
    def __init__(self, name: str):
        self.name = name


class _WorldGraph:
    def __init__(self):
        self.locations = {
            "office_lobby": _Loc("Office Lobby"),
            "apartment": _Loc("Apartment"),
            "workplace_lobby": _Loc("Workplace Lobby"),
        }


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


# ============================================================================
# UNIT TESTS (with mocked LLM responses)
# ============================================================================

@pytest.mark.asyncio
async def test_location_extractor_should_attempt_mocked_rejects_question(monkeypatch):
    """Unit test: _should_attempt rejects questions via mocked LLM."""
    extractor = LocationExtractor(model="test-model")

    async def fake_post_negative(self, url, headers=None, json=None):
        # Mock: LLM says this is NOT a movement intent
        return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": false}'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post_negative, raising=True)

    result = await extractor._should_attempt("Can we go to Office Lobby?")
    assert result is False


@pytest.mark.asyncio
async def test_location_extractor_should_attempt_mocked_accepts_command(monkeypatch):
    """Unit test: _should_attempt accepts explicit commands via mocked LLM."""
    extractor = LocationExtractor(model="test-model")

    async def fake_post_positive(self, url, headers=None, json=None):
        # Mock: LLM says this IS a movement intent
        return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post_positive, raising=True)

    result = await extractor._should_attempt("go to office lobby")
    assert result is True


@pytest.mark.asyncio
async def test_location_extractor_mocked_returns_destination_for_explicit_command(monkeypatch):
    """Unit test: Full extraction with mocked LLM responses."""
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    call_count = {"count": 0}

    async def fake_post_two_step(self, url, headers=None, json=None):
        """First call: classification, Second call: extraction."""
        call_count["count"] += 1
        
        if call_count["count"] == 1:
            # First call: _should_attempt returns true
            return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})
        else:
            # Second call: full extraction
            return _Resp(200, {"choices": [{"message": {"content": '{"intent":"MOVE","destination_id":"office_lobby","confidence":0.95,"destination_text":"Office Lobby"}'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post_two_step, raising=True)

    res = await extractor.extract("go to Office Lobby", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id == "office_lobby"
    assert res.confidence >= 0.9


@pytest.mark.asyncio
async def test_location_extractor_mocked_rejects_nonexistent_destination(monkeypatch):
    """Unit test: Extractor classifies as movement but destination doesn't exist in graph."""
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    call_count = {"count": 0}

    async def fake_post(self, url, headers=None, json=None):
        call_count["count"] += 1
        
        if call_count["count"] == 1:
            # Classification: yes it's a movement intent
            return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})
        else:
            # Extraction: but with non-existent destination ID
            return _Resp(200, {"choices": [{"message": {"content": '{"intent":"MOVE","destination_id":"invalid_location","confidence":0.8,"destination_text":"Invalid Location"}'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)

    res = await extractor.extract("go to invalid location", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id == "invalid_location"
    # Intent is MOVE, but note: the chat endpoint should validate this against the graph


@pytest.mark.asyncio
async def test_location_extractor_mocked_natural_language_variation(monkeypatch):
    """Unit test: Handles natural language 'i'm going to X' variations."""
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    call_count = {"count": 0}

    async def fake_post(self, url, headers=None, json=None):
        call_count["count"] += 1
        
        if call_count["count"] == 1:
            # Classification: yes it's a movement intent (even with 'I'm going')
            return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})
        else:
            # Extraction
            return _Resp(200, {"choices": [{"message": {"content": '{"intent":"MOVE","destination_id":"workplace_lobby","confidence":0.92,"destination_text":"Workplace"}'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)

    res = await extractor.extract("actually I'm going to your workplace see you in a bit", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id == "workplace_lobby"


@pytest.mark.asyncio
async def test_location_extractor_does_not_trigger_on_questions(monkeypatch):
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    async def fake_post(self, url, headers=None, json=None):
        # Mock: Classification returns false
        return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": false}'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)

    res = await extractor.extract("Can we go to Office Lobby?", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.NONE
    assert res.destination_id is None


@pytest.mark.asyncio
async def test_location_extractor_returns_destination_id_for_explicit_go_to(monkeypatch):
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    call_count = {"count": 0}

    async def fake_post(self, url, headers=None, json=None):
        call_count["count"] += 1
        if call_count["count"] == 1:
            # Classification: yes
            return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})
        else:
            # Extraction
            return _Resp(200, {"choices": [{"message": {"content": '{"intent":"MOVE","destination_id":"office_lobby","confidence":0.9,"destination_text":"Office Lobby"}'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)

    res = await extractor.extract("go to Office Lobby", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id == "office_lobby"
    assert res.confidence >= 0.5
