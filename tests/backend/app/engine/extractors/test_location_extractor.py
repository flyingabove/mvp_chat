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


# ============================================================================
# ERROR HANDLING TESTS (network timeouts, malformed responses, etc.)
# ============================================================================

@pytest.mark.asyncio
async def test_location_extractor_handles_network_timeout_on_classification(monkeypatch):
    """Test: Network timeout on _should_attempt returns False gracefully."""
    extractor = LocationExtractor(model="test-model")

    async def fake_post_timeout(self, url, headers=None, json=None):
        raise TimeoutError("Connection timeout")

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post_timeout, raising=True)

    # Should not raise, but return False
    result = await extractor._should_attempt("go to office")
    assert result is False


@pytest.mark.asyncio
async def test_location_extractor_handles_network_timeout_on_extraction(monkeypatch):
    """Test: Network timeout on extract() returns NONE intent gracefully."""
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    call_count = {"count": 0}

    async def fake_post(self, url, headers=None, json=None):
        call_count["count"] += 1
        if call_count["count"] == 1:
            # Classification succeeds
            return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})
        else:
            # Extraction fails with timeout
            raise TimeoutError("Connection timeout on extraction")

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)

    # Should not raise, but return NONE intent
    res = await extractor.extract("go to office", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.NONE
    assert res.destination_id is None


@pytest.mark.asyncio
async def test_location_extractor_handles_malformed_json_response(monkeypatch):
    """Test: Malformed JSON in LLM response returns NONE intent."""
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    call_count = {"count": 0}

    async def fake_post(self, url, headers=None, json=None):
        call_count["count"] += 1
        if call_count["count"] == 1:
            # Classification succeeds
            return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})
        else:
            # Extraction returns invalid JSON
            return _Resp(200, {"choices": [{"message": {"content": 'NOT VALID JSON {{'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)

    # Should not raise, but return NONE intent
    res = await extractor.extract("go to office", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.NONE
    assert res.destination_id is None


@pytest.mark.asyncio
async def test_location_extractor_handles_http_error_on_extraction(monkeypatch):
    """Test: HTTP 500 on extraction returns NONE intent."""
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    call_count = {"count": 0}

    async def fake_post(self, url, headers=None, json=None):
        call_count["count"] += 1
        if call_count["count"] == 1:
            # Classification succeeds
            return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})
        else:
            # Extraction fails with HTTP 500
            return _Resp(500, {})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)

    # Should not raise, but return NONE intent
    res = await extractor.extract("go to office", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.NONE
    assert res.destination_id is None


@pytest.mark.asyncio
async def test_location_extractor_handles_missing_json_keys(monkeypatch):
    """Test: Response missing expected JSON keys returns NONE intent."""
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    call_count = {"count": 0}

    async def fake_post(self, url, headers=None, json=None):
        call_count["count"] += 1
        if call_count["count"] == 1:
            # Classification succeeds
            return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})
        else:
            # Extraction returns JSON but missing "content" key in message
            return _Resp(200, {"choices": [{"message": {}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)

    # Should not raise, but return NONE intent
    res = await extractor.extract("go to office", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.NONE
    assert res.destination_id is None


# ============================================================================
# CONVERSATION HISTORY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_location_extractor_includes_conversation_log_in_messages(monkeypatch):
    """Test: conversation_log is passed and included in API request messages."""
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    captured_payloads = []

    async def fake_post_capture(self, url, headers=None, json=None):
        captured_payloads.append(json)
        # Return simple responses for both calls
        if len(captured_payloads) == 1:
            return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})
        else:
            return _Resp(200, {"choices": [{"message": {"content": '{"intent":"MOVE","destination_id":"office_lobby","confidence":0.9,"destination_text":"Office Lobby"}'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post_capture, raising=True)

    conversation_log = [
        {"role": "system", "content": "You are a game master."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "Where can I go?"},
        {"role": "assistant", "content": "You can visit the Office Lobby or Apartment."},
    ]

    res = await extractor.extract(
        "go to Office Lobby",
        world_graph=world_graph,
        conversation_log=conversation_log
    )

    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.MOVE

    # Verify conversation history was included in both API calls (minus system messages)
    # First call: _should_attempt
    first_payload = captured_payloads[0]
    first_messages = first_payload["messages"]
    # Should have system + 4 non-system history messages + current user message = 6 messages
    assert len(first_messages) >= 5  # at least system + some history + user

    # Second call: extract
    second_payload = captured_payloads[1]
    second_messages = second_payload["messages"]
    # Should have system + history + extraction request
    assert len(second_messages) >= 5

    # Verify history content appears (non-system messages from conversation_log)
    all_content = " ".join([m.get("content", "") for m in second_messages])
    assert "Hello" in all_content or "Hi there" in all_content


@pytest.mark.asyncio
async def test_location_extractor_should_attempt_with_conversation_log(monkeypatch):
    """Test: _should_attempt includes conversation history when provided."""
    extractor = LocationExtractor(model="test-model")

    captured_payload = {}

    async def fake_post_capture(self, url, headers=None, json=None):
        captured_payload.update(json)
        return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post_capture, raising=True)

    conversation_log = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Previous message"},
        {"role": "assistant", "content": "Previous response"},
    ]

    result = await extractor._should_attempt("go to office", conversation_log=conversation_log)
    assert result is True

    # Verify messages include history (system messages from log are filtered out)
    messages = captured_payload.get("messages", [])
    # Should have: classifier system + 2 non-system history + current user message = 4
    assert len(messages) >= 3

    # Check that conversation history content is present
    all_content = " ".join([m.get("content", "") for m in messages])
    assert "Previous message" in all_content or "Previous response" in all_content


@pytest.mark.asyncio
async def test_location_extractor_limits_conversation_log_to_extractor_turns(monkeypatch):
    """Test: conversation_log is limited to EXTRACTOR_TURNS messages."""
    from backend.app.config.settings import EXTRACTOR_TURNS

    extractor = LocationExtractor(model="test-model")

    captured_payload = {}

    async def fake_post_capture(self, url, headers=None, json=None):
        captured_payload.update(json)
        return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": false}'}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post_capture, raising=True)

    # Create a long conversation log with more than EXTRACTOR_TURNS messages
    conversation_log = [{"role": "system", "content": "System"}]
    for i in range(20):
        conversation_log.append({"role": "user", "content": f"User message {i}"})
        conversation_log.append({"role": "assistant", "content": f"Assistant response {i}"})

    await extractor._should_attempt("go to office", conversation_log=conversation_log)

    # Verify the messages are limited
    messages = captured_payload.get("messages", [])
    # Should be: 1 system (classifier) + up to EXTRACTOR_TURNS history + 1 user = at most EXTRACTOR_TURNS + 2
    non_system_history = [m for m in messages if m.get("role") != "system" and "User message:" not in m.get("content", "")]
    assert len(non_system_history) <= EXTRACTOR_TURNS


# ============================================================================
# INTEGRATION PLAYBACK (uses real OpenAI — scenario class lives in backend)
# ============================================================================

from backend.app.integration_playback.scenarios.scenario_location_extractor_llm import LocationExtractorScenario


@pytest.mark.integration
def test_location_extractor_playback():
    LocationExtractorScenario.run_as_test()


@pytest.mark.asyncio
async def test_should_attempt_survives_a_rate_limit(monkeypatch):
    """BL-30: a 429 (e.g. during an arena gate) used to read as 'no movement'."""
    import asyncio as _asyncio
    extractor = LocationExtractor(model="test-model")
    calls = {"n": 0}

    class _Limited(_Resp):
        text = "Rate limit reached. Please try again in 5ms."
        headers = {}

    async def fake_post(self, url, headers=None, json=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Limited(429, {})
        return _Resp(200, {"choices": [{"message": {"content": '{"is_movement_intent": true}'}}]})

    async def no_wait(seconds):
        return None

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)
    monkeypatch.setattr(_asyncio, "sleep", no_wait)
    assert await extractor._should_attempt("go to office lobby") is True
    assert calls["n"] == 2
