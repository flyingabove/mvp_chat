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
        }


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_location_extractor_does_not_trigger_on_questions(monkeypatch):
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    async def boom(*args, **kwargs):
        raise AssertionError("Extractor should not call upstream for questions")

    # Patch the AsyncClient.post method used internally.
    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", boom, raising=True)

    res = await extractor.extract("Can we go to Office Lobby?", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.NONE
    assert res.destination_id is None


@pytest.mark.asyncio
async def test_location_extractor_returns_destination_id_for_explicit_go_to(monkeypatch):
    extractor = LocationExtractor(model="test-model")
    world_graph = _WorldGraph()

    async def fake_post(self, url, headers=None, json=None):
        # Ensure we're sending a chat completions request
        assert "chat/completions" in url
        content = '{"intent":"MOVE","destination_id":"office_lobby","confidence":0.9,"destination_text":"Office Lobby"}'
        return _Resp(200, {"choices": [{"message": {"content": content}}]})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=True)

    res = await extractor.extract("go to Office Lobby", world_graph=world_graph)
    assert isinstance(res, LocationExtraction)
    assert res.intent == LocationIntent.MOVE
    assert res.destination_id == "office_lobby"
    assert res.confidence >= 0.5
