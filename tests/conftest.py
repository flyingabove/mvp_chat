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
# AUTO-LOAD .env.test IF IT EXISTS
# ---------------------------------------------------------------------------
def _load_env_test():
    """Load .env.test file if it exists (for local development)."""
    env_test_path = Path(__file__).parent.parent / ".env.test"

    if not env_test_path.exists():
        return

    # Simple .env parser (no external dependency required)
    with open(env_test_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes if present
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                # Only set if not already in environment (don't override CI secrets)
                if key and key not in os.environ:
                    os.environ[key] = value


# Load on import
_load_env_test()


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


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def openai_api_key() -> str | None:
    """Get the OpenAI API key if available.

    Returns None if not set (use with pytest.mark.skipif or require_api_key fixture).
    """
    return os.environ.get("OPENAI_API_KEY") or None


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
