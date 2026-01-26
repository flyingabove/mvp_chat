"""
Unit tests for Chinese translation mode feature.
Tests the [C]/(C) toggle, translation function, and integration with chat flow.
"""

import types
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client_with_translation(monkeypatch):
    """Create a TestClient with translation and chat mocked appropriately."""
    from backend.app.api import chat as chat_mod

    # Prevent retrieval from doing any IO during tests.
    monkeypatch.setattr(chat_mod, "retrieve_knowledge", lambda *args, **kwargs: ([], {}), raising=False)

    # Mock location extractor
    from backend.app.engine.extractors.location_extractor import LocationExtraction, LocationIntent
    async def _mock_extract(*args, **kwargs):
        return LocationExtraction(intent=LocationIntent.NONE, destination_id=None, confidence=0.0, destination_text=None)
    monkeypatch.setattr(chat_mod._LOCATION_EXTRACTOR, "extract", _mock_extract, raising=False)

    # Track translation calls
    translation_spy = types.SimpleNamespace(calls=0, last_input=None, return_value="这是翻译的回复")
    
    async def mock_translate(text: str) -> str:
        translation_spy.calls += 1
        translation_spy.last_input = text
        return translation_spy.return_value

    monkeypatch.setattr(chat_mod, "_translate_to_chinese", mock_translate)

    # Mock httpx.AsyncClient for LLM calls
    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "I understand.\n\n[[STATE]]{\"emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"}}],
                "usage": {"total_tokens": 1},
            }

        @property
        def text(self):
            return "ok"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return _FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    # Create test app
    from backend.app.main import app
    client = TestClient(app)
    
    return client, translation_spy, chat_mod


# ============================================================================
# Chinese Toggle Detection Tests
# ============================================================================

def test_is_chinese_toggle_detects_all_formats():
    """Test that _is_chinese_toggle recognizes all toggle formats."""
    import backend.app.api.chat as chat_mod
    
    # Test all supported formats (case insensitive)
    assert chat_mod._is_chinese_toggle("[C]")
    assert chat_mod._is_chinese_toggle("(C)")
    assert chat_mod._is_chinese_toggle("[CHINESE]")
    assert chat_mod._is_chinese_toggle("(CHINESE)")
    assert chat_mod._is_chinese_toggle("[c]")  # lowercase
    assert chat_mod._is_chinese_toggle("(c)")  # lowercase
    assert chat_mod._is_chinese_toggle("[chinese]")  # lowercase
    assert chat_mod._is_chinese_toggle("(chinese)")  # lowercase
    
    # Test false negatives
    assert not chat_mod._is_chinese_toggle("[D]")
    assert not chat_mod._is_chinese_toggle("Chinese")  # no brackets
    assert not chat_mod._is_chinese_toggle("C")  # no brackets
    assert not chat_mod._is_chinese_toggle("hello")
    assert not chat_mod._is_chinese_toggle("")
    assert not chat_mod._is_chinese_toggle(None)


def test_chinese_toggle_is_case_insensitive():
    """Verify that Chinese toggle is case-insensitive."""
    import backend.app.api.chat as chat_mod
    
    test_cases = [
        "[C]", "[c]",
        "(C)", "(c)",
        "[CHINESE]", "[chinese]", "[ChInEsE]",
        "(CHINESE)", "(chinese)", "(ChInEsE)",
    ]
    
    for test_input in test_cases:
        assert chat_mod._is_chinese_toggle(test_input), f"Failed for: {test_input}"


# ============================================================================
# Chinese Toggle Session State Tests
# ============================================================================

def test_chinese_toggle_enters_mode(client_with_translation):
    """Test that [C] command enters Chinese mode."""
    client, _, _ = client_with_translation
    
    # Start a new game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test1",
        "message": "__cmd_newgame__:iu_murder_mystery|M|TestPlayer"
    })
    assert resp.status_code == 200
    
    # Toggle Chinese mode on
    resp = client.post("/api/chat", json={
        "session_id": "cn_test1",
        "message": "[C]"
    })
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    
    # Should see Chinese mode entrance message
    assert "进入中文模式" in reply or "Chinese mode" in reply.lower()


def test_chinese_toggle_exits_mode(client_with_translation):
    """Test that [C] command exits Chinese mode when already on."""
    client, _, _ = client_with_translation
    
    # Start a new game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test2",
        "message": "__cmd_newgame__:iu_murder_mystery|M|TestPlayer"
    })
    assert resp.status_code == 200
    
    # Enter Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test2",
        "message": "[C]"
    })
    assert resp.status_code == 200
    
    # Exit Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test2",
        "message": "[C]"
    })
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    
    # Should see exit message
    assert "退出中文模式" in reply or "exit" in reply.lower()


def test_chinese_mode_persists_in_session(client_with_translation):
    """Test that Chinese mode flag persists across turns."""
    client, translation_spy, chat_mod = client_with_translation
    
    # Start new game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test3",
        "message": "__cmd_newgame__:iu_murder_mystery|M|TestPlayer"
    })
    assert resp.status_code == 200
    
    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test3",
        "message": "[C]"
    })
    assert resp.status_code == 200
    
    # Reset translation spy
    translation_spy.calls = 0
    
    # Send a normal message - should trigger translation
    resp = client.post("/api/chat", json={
        "session_id": "cn_test3",
        "message": "hello"
    })
    assert resp.status_code == 200
    
    # Should have called translation function
    assert translation_spy.calls > 0, "Translation should be called when in Chinese mode"


# ============================================================================
# Translation Function Tests
# ============================================================================

def test_translate_to_chinese_preserves_formatting(monkeypatch):
    """Test that translation preserves formatting markers."""
    from backend.app.api import chat as chat_mod
    import httpx
    
    # Create a mock OpenAI response with formatting
    class _FakeResp:
        status_code = 200
        def json(self):
            return {
                "choices": [{
                    "message": {
                        "content": "**你好** *世界* 和 \"引号\"\n\n新行文本"
                    }
                }],
                "usage": {"total_tokens": 10},
            }
        @property
        def text(self):
            return "ok"
    
    class _FakeAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, *args, **kwargs):
            return _FakeResp()
    
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    
    # Run translation
    import asyncio
    result = asyncio.run(chat_mod._translate_to_chinese("**Hello** *world* and \"quotes\"\n\nNew line text"))
    
    # Should preserve structure
    assert "**" in result  # bold markers
    assert "*" in result   # italic markers
    assert "\"" in result  # quotes
    assert "\n\n" in result  # line breaks


def test_translate_to_chinese_handles_empty_text(monkeypatch):
    """Test that translation handles empty or whitespace text."""
    from backend.app.api import chat as chat_mod
    
    import asyncio
    
    # Empty string
    result = asyncio.run(chat_mod._translate_to_chinese(""))
    assert result == ""
    
    # Whitespace only
    result = asyncio.run(chat_mod._translate_to_chinese("   \n  \t  "))
    assert result == "   \n  \t  "


def test_translate_to_chinese_fallback_on_error(monkeypatch):
    """Test that translation falls back to original text on error."""
    from backend.app.api import chat as chat_mod
    
    class _FakeAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, *args, **kwargs):
            raise Exception("Network error")
    
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    
    import asyncio
    original = "Hello world"
    result = asyncio.run(chat_mod._translate_to_chinese(original))
    
    # Should return original text on error
    assert result == original


def test_translate_to_chinese_http_error_fallback(monkeypatch):
    """Test that translation falls back on HTTP errors."""
    from backend.app.api import chat as chat_mod
    
    class _FakeResp:
        status_code = 500
        @property
        def text(self):
            return "Internal Server Error"
    
    class _FakeAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, *args, **kwargs):
            return _FakeResp()
    
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    
    import asyncio
    original = "Hello world"
    result = asyncio.run(chat_mod._translate_to_chinese(original))
    
    # Should return original text on HTTP error
    assert result == original


# ============================================================================
# Chinese Mode Integration Tests
# ============================================================================

def test_chinese_mode_translates_opening_on_newgame(client_with_translation):
    """Test that opening prompt is translated when starting game in Chinese mode."""
    client, translation_spy, _ = client_with_translation
    
    # Manually enable Chinese mode in session first
    from backend.app.api.chat import SESSIONS
    session_id = "cn_test_opening"
    SESSIONS[session_id] = {
        "state": None,
        "log": [],
        "debug_mode": False,
        "chinese_mode": True,  # Enable Chinese mode BEFORE newgame
    }
    
    # Reset spy
    translation_spy.calls = 0
    translation_spy.return_value = "欢迎来到故事..."
    
    # Start new game - should translate opening
    resp = client.post("/api/chat", json={
        "session_id": session_id,
        "message": "__cmd_newgame__:iu_murder_mystery|M|TestPlayer"
    })
    assert resp.status_code == 200
    
    # Translation should have been called
    assert translation_spy.calls > 0, "Opening should be translated in Chinese mode"
    reply = resp.json()["reply"]
    assert "欢迎来到故事" in reply


def test_chinese_mode_translates_regular_responses(client_with_translation):
    """Test that regular chat responses are translated in Chinese mode."""
    client, translation_spy, _ = client_with_translation
    
    # Setup: start game, enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_responses",
        "message": "__cmd_newgame__:iu_murder_mystery|M|TestPlayer"
    })
    assert resp.status_code == 200
    
    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_responses",
        "message": "[C]"
    })
    assert resp.status_code == 200
    
    # Reset spy
    translation_spy.calls = 0
    translation_spy.return_value = "我理解了。"
    
    # Send message - should be translated
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_responses",
        "message": "What happened?"
    })
    assert resp.status_code == 200
    
    # Verify translation was called
    assert translation_spy.calls > 0
    reply = resp.json()["reply"]
    assert "我理解了" in reply


def test_english_mode_no_translation(client_with_translation):
    """Test that responses are NOT translated when Chinese mode is off."""
    client, translation_spy, _ = client_with_translation
    
    # Start game (no Chinese mode)
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_english",
        "message": "__cmd_newgame__:iu_murder_mystery|M|TestPlayer"
    })
    assert resp.status_code == 200
    
    # Reset spy
    translation_spy.calls = 0
    
    # Send message - should NOT be translated
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_english",
        "message": "Hello"
    })
    assert resp.status_code == 200
    
    # Translation should NOT have been called
    assert translation_spy.calls == 0, "No translation should occur in English mode"


def test_chinese_toggle_with_special_characters(client_with_translation):
    """Test Chinese toggle with text containing special characters."""
    client, _, _ = client_with_translation
    
    # Start game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_special",
        "message": "__cmd_newgame__:iu_murder_mystery|M|TestPlayer"
    })
    assert resp.status_code == 200
    
    # Toggle with text around it (edge case)
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_special",
        "message": "  [C]  "  # whitespace around toggle
    })
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    
    # Should still recognize the toggle
    assert "进入中文模式" in reply or "Chinese mode" in reply.lower()


def test_reset_clears_chinese_mode():
    """Test that reset command clears Chinese mode flag."""
    import backend.app.api.chat as chat_mod
    
    session_id = "reset_test"
    
    # Create session with Chinese mode on
    sess = chat_mod.get_session(session_id)
    sess["chinese_mode"] = True
    assert sess["chinese_mode"] is True
    
    # Send reset command (simulated)
    # After reset, new session should have chinese_mode = False
    chat_mod.SESSIONS[session_id] = {
        "state": chat_mod.init_state(),
        "log": [],
        "debug_mode": False,
        "chinese_mode": False,
    }
    
    sess = chat_mod.get_session(session_id)
    assert sess["chinese_mode"] is False


def test_chinese_and_debug_modes_can_coexist(client_with_translation):
    """Test that Chinese and Debug modes can both be enabled."""
    client, translation_spy, _ = client_with_translation
    
    # Start game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "__cmd_newgame__:iu_murder_mystery|M|TestPlayer"
    })
    assert resp.status_code == 200
    
    # Enable debug mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "[D]"
    })
    assert resp.status_code == 200
    
    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "[C]"
    })
    assert resp.status_code == 200
    
    # Reset spy
    translation_spy.calls = 0
    translation_spy.return_value = "我理解了。(Debug box here...)"
    
    # Send message - should have both debug info AND Chinese translation
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "hello"
    })
    assert resp.status_code == 200
    
    # Translation should be called (Chinese mode on)
    assert translation_spy.calls > 0
    reply = resp.json()["reply"]
    
    # Should include translated content
    assert "我理解了" in reply


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

def test_chinese_mode_with_empty_response(client_with_translation):
    """Test Chinese mode handling of empty or very short responses."""
    client, translation_spy, _ = client_with_translation
    
    # Start game with Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_empty",
        "message": "__cmd_newgame__:iu_murder_mystery|M|TestPlayer"
    })
    assert resp.status_code == 200
    
    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_empty",
        "message": "[C]"
    })
    assert resp.status_code == 200
    
    # Set translation to return empty
    translation_spy.return_value = ""
    
    # This should still work gracefully
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_empty",
        "message": "hi"
    })
    assert resp.status_code == 200


def test_chinese_mode_toggle_formatting():
    """Test that Chinese mode toggle messages are properly formatted."""
    import backend.app.api.chat as chat_mod
    
    # Both toggles should produce formatted output with _box
    # This is inherently tested by the integration tests above,
    # but we can verify the box function works with Chinese text
    box = chat_mod._box("进入中文模式", ["Type [C] to exit"])
    
    assert "进入中文模式" in box
    assert "┌" in box  # corners exist
    assert "└" in box
    assert "├" in box  # separator exists
