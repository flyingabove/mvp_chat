# tests/conftest.py
"""
Pytest configuration for the test suite.

POLICY: NO TESTS MAY BE SKIPPED — EVER.
========================================
All tests must run and pass in every environment (local, CI, Railway).
If a test needs an API key, the key MUST be available. If it isn't,
the test MUST fail (not skip). pytest.skip() is banned.

This module:
1. Auto-loads .env.test for integration tests (if it exists)
2. Provides fixtures for API key checking (hard fail, never skip)
3. Configures async test support
4. Enforces the no-skip policy via a pytest hook

USAGE:
------
For local development:
1. Copy .env.test.example to .env.test
2. Fill in your API keys
3. Run: pytest

For CI/CD (Railway, GitHub Actions):
- Set OPENAI_API_KEY as an environment variable / secret
- All tests run unconditionally — no skips allowed
"""

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# XFAIL POLICY
# ---------------------------------------------------------------------------
_ALLOWED_XFAIL_NODEIDS = {
    "tests/backend/app/api/test_prompt_engine.py::test_iu_identity_correction",
}


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
def openai_api_key() -> str:
    """Get the OpenAI API key. Fails hard if not available.

    POLICY: No skipping. If the key is missing, the test fails.
    """
    key = get_openai_api_key()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is required but not set. "
            "Set it via environment variable or .env.test file. "
            "Tests are NEVER allowed to skip."
        )
    return key


@pytest.fixture
def require_openai_api_key(openai_api_key):
    """Require OPENAI_API_KEY — fails hard if missing (never skips).

    Usage:
        def test_something(require_openai_api_key):
            # This test will FAIL (not skip) if API key is missing
            ...
    """
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
    """Enforce xfail policy: only allow explicit quarantine nodeids.

    Any xfail marker outside the allowlist is a hard error at collection time.
    """
    disallowed = []
    for item in items:
        if item.get_closest_marker("xfail") and item.nodeid not in _ALLOWED_XFAIL_NODEIDS:
            disallowed.append(item.nodeid)

    if disallowed:
        joined = "\n".join(f"- {n}" for n in disallowed)
        raise pytest.UsageError(
            "POLICY VIOLATION: xfail marker used outside allowlist.\n"
            "Only explicitly quarantined tests may use xfail.\n"
            f"Allowed:\n- {next(iter(_ALLOWED_XFAIL_NODEIDS))}\n"
            f"Found disallowed xfail markers:\n{joined}"
        )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Enforce NO-SKIP policy: convert any skip into a hard failure.

    This hook runs after every test phase (setup, call, teardown).
    If any test tries to skip itself (via pytest.skip(), @pytest.mark.skip,
    @pytest.mark.skipif, or unittest.skip), it will be converted to a
    FAILURE with a clear error message.

    POLICY: No test may be skipped for any reason in any environment.
    """
    outcome = yield
    report = outcome.get_result()

    # Allow only explicit xfail quarantines (report.skipped + wasxfail).
    wasxfail = getattr(report, "wasxfail", None)
    if report.skipped and wasxfail:
        if item.nodeid in _ALLOWED_XFAIL_NODEIDS:
            return
        report.outcome = "failed"
        report.longrepr = (
            f"POLICY VIOLATION: Test '{item.nodeid}' used xfail but is not allowlisted.\n"
            f"xfail reason: {wasxfail}\n\n"
            f"Only this test may xfail:\n"
            f"- {next(iter(_ALLOWED_XFAIL_NODEIDS))}"
        )
        return

    if report.skipped:
        report.outcome = "failed"
        report.longrepr = (
            f"POLICY VIOLATION: Test '{item.nodeid}' attempted to skip.\n"
            f"Reason: {report.longrepr}\n\n"
            f"NO TESTS MAY BE SKIPPED — EVER.\n"
            f"All tests must run and pass in every environment (local, CI, Railway).\n"
            f"Fix the test or fix the environment, but do not skip."
        )


# ---------------------------------------------------------------------------
# ASYNC SUPPORT
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy for async tests."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
