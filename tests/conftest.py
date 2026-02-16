# tests/conftest.py
"""
Pytest configuration for the test suite.

This module:
1. Auto-loads .env.test for integration tests (if it exists)
2. Provides fixtures for API key checking
3. Configures async test support

USAGE:
------
For local integration testing:
1. Copy .env.test.example to .env.test
2. Fill in your API keys
3. Run: pytest -m integration

For CI/CD:
- Set OPENAI_API_KEY as a repository secret
- The tests will auto-detect and use it
"""

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# CREDENTIAL LOADING (centralized in backend.app.config.credentials)
# ---------------------------------------------------------------------------
from backend.app.config.credentials import get_openai_api_key, _load_env_test_once

# Load .env.test on import (env vars always take priority over .env.test)
_load_env_test_once()


# ---------------------------------------------------------------------------
# STORY / CHARACTER AUTO-DISCOVERY
# ---------------------------------------------------------------------------
def _discover_stories() -> list[dict]:
    """Auto-discover all available story configs (sorted by folder prefix)."""
    stories_dir = Path(__file__).parent.parent / "backend" / "app" / "stories"
    results = []
    if not stories_dir.exists():
        return results
    import json as _json
    for subdir in sorted(stories_dir.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("__"):
            continue
        for p in sorted(subdir.glob("*.json")):
            if p.name.endswith("_world.json"):
                continue
            try:
                cfg = _json.loads(p.read_text(encoding="utf-8"))

                # Backfill legacy main_character for tests when using characters list.
                if "main_character" not in cfg and cfg.get("characters"):
                    chars = cfg.get("characters") or []
                    main = next((c for c in chars if c.get("is_main")), chars[0] if chars else {})
                    cfg["main_character"] = {
                        "key": main.get("key", "main"),
                        "name": main.get("name", ""),
                        "role": main.get("role", ""),
                        "knowledge_character_id": main.get("knowledge_character_id", ""),
                        "uuid": main.get("uuid", ""),
                    }
            except Exception:
                continue
            results.append({
                "id": str(cfg.get("id") or p.stem).strip(),
                "folder": subdir.name,
                "path": str(p),
                "config": cfg,
            })
    return results


def first_story_id() -> str:
    """Return the ID of the first available story (sorted by folder)."""
    stories = _discover_stories()
    if not stories:
        raise RuntimeError("No stories found in backend/app/stories/")
    return stories[0]["id"]


def first_story_folder() -> str:
    """Return the folder name of the first available story."""
    stories = _discover_stories()
    if not stories:
        raise RuntimeError("No stories found in backend/app/stories/")
    return stories[0]["folder"]


def first_character_id() -> str:
    """Return the first character directory name from knowledge/characters/."""
    chars_dir = Path(__file__).parent.parent / "backend" / "app" / "knowledge" / "characters"
    if not chars_dir.exists():
        return ""
    dirs = sorted(p.name for p in chars_dir.iterdir() if p.is_dir())
    return dirs[0] if dirs else ""


def all_character_ids() -> list[str]:
    """Return all character directory names from knowledge/characters/ (sorted)."""
    chars_dir = Path(__file__).parent.parent / "backend" / "app" / "knowledge" / "characters"
    if not chars_dir.exists():
        return []
    return sorted(p.name for p in chars_dir.iterdir() if p.is_dir())


def story_knowledge_character_id(story_id: str) -> str:
    """Return the knowledge_character_id for a given story_id."""
    for s in _discover_stories():
        if s["id"] == story_id:
            return s["config"].get("main_character", {}).get("knowledge_character_id", "")
    return ""


def all_stories() -> list[dict]:
    """Return all discovered stories."""
    return _discover_stories()


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def openai_api_key() -> str | None:
    """Get the OpenAI API key if available.

    Returns None if not set (use with pytest.mark.skipif or require_api_key fixture).
    """
    return get_openai_api_key() or None


@pytest.fixture
def require_openai_api_key(openai_api_key):
    """Skip test if OPENAI_API_KEY is not available.

    Usage:
        def test_something(require_openai_api_key):
            # This test only runs if API key is set
            ...
    """
    if not openai_api_key:
        pytest.skip("OPENAI_API_KEY not set - skipping integration test")
    return openai_api_key


# ---------------------------------------------------------------------------
# PYTEST HOOKS
# ---------------------------------------------------------------------------
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test (requires API keys)"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow-running"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip integration tests if no API key is set (unless explicitly requested)."""
    # Check if integration tests are explicitly requested
    running_integration = config.getoption("-m", default="") == "integration"

    if running_integration:
        # User explicitly wants integration tests - don't auto-skip
        return

    # For normal test runs, integration tests are skipped via their own skipif decorators
    # This hook could add additional behavior if needed


# ---------------------------------------------------------------------------
# ASYNC SUPPORT
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy for async tests."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
