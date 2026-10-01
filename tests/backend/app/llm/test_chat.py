"""Provider selection (gemini / openai / ollama) and the single get_chat entry point."""
import asyncio
import json

import httpx
import pytest

from backend.app.llm import chat
from backend.app.llm import factory


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_MODEL", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")


def test_default_is_gemini_3_8_flash():
    cfg = chat.resolve_chat_config()
    assert (cfg.provider, cfg.model, cfg.api_key) == ("gemini", "gemini-3.8-flash", "g-key")
    assert cfg.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"


def test_env_switches_provider_and_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    cfg = chat.resolve_chat_config()
    assert (cfg.provider, cfg.model, cfg.api_key) == ("openai", "gpt-4o-mini", "o-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    assert chat.resolve_chat_config().model == "gpt-4o"


def test_ollama_needs_no_key_and_base_url_is_overridable(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "1")          # off by default (tests/backend/app/llm/test_ollama_switch.py)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://box:11434/v1/")
    cfg = chat.resolve_chat_config()
    assert (cfg.provider, cfg.base_url, cfg.model) == ("ollama", "http://box:11434/v1", "llama3.1:8b")


def test_explicit_provider_does_not_inherit_llm_model(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash-lite")
    assert chat.resolve_chat_config("openai").model == "gpt-4o-mini"
    assert chat.resolve_chat_config("openai", "gpt-4o").model == "gpt-4o"


def test_missing_gemini_key_falls_back_to_openai(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr(chat, "get_gemini_api_key", lambda: "")
    monkeypatch.setitem(chat._PROVIDERS, "gemini", chat._Spec(chat.GEMINI_BASE_URL, chat.GEMINI_DEFAULT_MODEL, lambda: ""))
    assert chat.resolve_chat_config().provider == "openai"


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        chat.resolve_chat_config("claude-ish")


def test_get_chat_posts_to_selected_provider(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "gemini-3.8-flash",
            "choices": [{"message": {"content": "Arr."}}],
            "usage": {"total_tokens": 3},
        })

    monkeypatch.setattr(factory, "_shared_httpx_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = asyncio.run(chat.get_chat("Be a pirate.", [{"role": "user", "content": "Hi"}], max_tokens=64))
    assert result.text == "Arr."
    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert seen["auth"] == "Bearer g-key"
    assert seen["body"]["model"] == "gemini-3.8-flash"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "Be a pirate."}
    factory.reset_shared_state_for_tests()


def test_only_gemini_has_a_fallback_model():
    assert chat.resolve_chat_config().fallback_model == "gemini-3.5-flash-lite"
    assert chat.resolve_chat_config("openai").fallback_model == ""
