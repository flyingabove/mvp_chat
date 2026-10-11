"""Owner decision 2026-10-01: Ollama is off unless OLLAMA_ENABLED=1; Gemini + Jev (or OpenAI + Jev) are the providers.

The switch has one definition (`llm/ollama_switch.py`) and every Ollama-only entry point refuses, with one clear
message, instead of trying to connect while it is off.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.llm.chat import resolve_chat_config
from backend.app.llm.ollama_switch import OllamaDisabledError, ollama_enabled, require_ollama

REPO = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("value, expected", [
    (None, False), ("", False), ("0", False), ("false", False), ("off", False), ("nonsense", False),
    ("1", True), ("true", True), ("YES", True), (" on ", True),
])
def test_the_switch_is_off_unless_explicitly_truthy(value, expected):
    env = {} if value is None else {"OLLAMA_ENABLED": value}
    assert ollama_enabled(env) is expected


def test_require_ollama_names_the_variable_and_the_alternatives():
    with pytest.raises(OllamaDisabledError, match="OLLAMA_ENABLED=1") as error:
        require_ollama("the test", {})
    assert "Gemini" in str(error.value) and "the test" in str(error.value)
    require_ollama("the test", {"OLLAMA_ENABLED": "1"})   # on: no error


def test_the_ollama_provider_is_refused_while_off_and_resolves_when_on():
    with pytest.raises(OllamaDisabledError):
        resolve_chat_config("ollama", env={})
    with pytest.raises(ValueError):                       # it is a ValueError, like any unusable provider name
        resolve_chat_config(env={"LLM_PROVIDER": "ollama"})
    assert resolve_chat_config("ollama", env={"OLLAMA_ENABLED": "1"}).provider == "ollama"


def test_the_other_providers_are_unaffected():
    assert resolve_chat_config("gemini", env={"GEMINI_API_KEY": "k"}).provider == "gemini"
    assert resolve_chat_config("openai", env={}).provider == "openai"


def test_settings_exposes_the_switch():
    from backend.app.config import settings
    assert isinstance(settings.OLLAMA_ENABLED, bool)


@pytest.fixture
def switch_off(monkeypatch):
    monkeypatch.delenv("OLLAMA_ENABLED", raising=False)


@pytest.fixture
def switch_on(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "1")


# ------------------------------------------------------------------------------ the debug evaluator's local mode
async def test_debug_engine_local_mode_does_not_connect_while_off(switch_off, monkeypatch):
    import httpx
    from backend.app.api import debug_engine

    def forbidden(*args, **kwargs):
        raise AssertionError("no connection may be attempted while Ollama is off")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    status = await debug_engine.check_ollama()
    assert status["available"] is False and status["models"] == [] and status["disabled"] is True
    with pytest.raises(OllamaDisabledError):
        await debug_engine.ollama_generate("llama3.1:8b", "sys", "user")


# ----------------------------------------------------------------------------------------------- the scripts
def test_the_terrace_simulation_refuses_while_off_and_passes_when_on(switch_off, monkeypatch):
    from scripts.terrace_ollama_sim import require_switch
    with pytest.raises(SystemExit, match="OLLAMA_ENABLED=1"):
        require_switch()
    monkeypatch.setenv("OLLAMA_ENABLED", "1")
    require_switch()


def test_the_local_debug_launcher_refuses_while_off_and_passes_when_on(switch_off, monkeypatch):
    from scripts.scorer.story_agent_ui import require_switch
    with pytest.raises(SystemExit, match="OLLAMA_ENABLED=1"):
        require_switch()
    monkeypatch.setenv("OLLAMA_ENABLED", "1")
    require_switch()


# ----------------------------------------------------------------------------------------------- the arena
@pytest.fixture
def arena_cli(monkeypatch):
    skill = str(REPO / ".claude" / "skills" / "promote-to-prod")
    monkeypatch.syspath_prepend(skill)
    for name in [n for n in sys.modules if n == "arena" or n.startswith("arena.")]:
        monkeypatch.delitem(sys.modules, name)
    import arena.cli as cli
    return cli


async def test_the_offline_arena_refuses_while_off(arena_cli, switch_off):
    args = SimpleNamespace(ollama_url="http://127.0.0.1:11434/v1", ollama_model="llama3.1:8b", judges=["jev"])
    with pytest.raises(SystemExit, match="OLLAMA_ENABLED=1"):
        await arena_cli.run_local(args)


async def test_the_hosted_arena_refuses_an_ollama_judge_while_off(arena_cli, switch_off):
    args = SimpleNamespace(ollama_url="http://127.0.0.1:11434/v1", ollama_model="llama3.1:8b", judges=["jev", "ollama"])
    with pytest.raises(SystemExit, match="OLLAMA_ENABLED=1"):
        await arena_cli.run_hosted(args, stages=())


def test_the_arena_servers_inherit_the_switch(arena_cli, switch_on):
    """The temporary local servers run settings.py in a child process, so the child must see the switch on."""
    from arena.local_release import ollama_env
    assert ollama_env("m")["OLLAMA_ENABLED"] == "1"
