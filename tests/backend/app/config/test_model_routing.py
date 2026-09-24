"""OPENAI_BASE_URL / OPENAI_MODEL route every non-storyteller model call so a
locally started game can run fully offline on Ollama (arena local mode).
Defaults must stay exactly the production values."""
import importlib
from pathlib import Path

import backend.app.config.settings as settings

GAME_CALL_SITES = [
    "backend/app/api/prompt_engine.py",
    "backend/app/engine/extractors/location_extractor.py",
    "backend/app/engine/extractors/knowledge_resolution_extractor.py",
    "backend/app/engine/extractors/turn_extractor.py",
    "backend/app/knowledge/runtime/dialogue_extractor.py",
]


def test_defaults_are_production_values(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    s = importlib.reload(settings)
    assert s.OPENAI_BASE_URL == "https://api.openai.com/v1"
    assert s.OPENAI_MODEL == "gpt-4o-mini"


def test_env_overrides_point_calls_at_ollama(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1/")
    monkeypatch.setenv("OPENAI_MODEL", "llama3.1:8b")
    try:
        s = importlib.reload(settings)
        assert s.OPENAI_BASE_URL == "http://127.0.0.1:11434/v1"
        assert s.OPENAI_MODEL == "llama3.1:8b"
    finally:
        monkeypatch.delenv("OPENAI_BASE_URL")
        monkeypatch.delenv("OPENAI_MODEL")
        importlib.reload(settings)


def test_no_game_call_site_hardcodes_the_openai_url():
    root = Path(__file__).resolve().parents[4]
    for rel in GAME_CALL_SITES:
        assert "https://api.openai.com" not in (root / rel).read_text(encoding="utf-8"), rel
