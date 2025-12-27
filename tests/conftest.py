from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is importable when running tests outside Docker.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


import os
import pytest
from pathlib import Path

@pytest.fixture(scope="session", autouse=True)
def ensure_indexes_built():
    """
    Integration tests REQUIRE real built artifacts.

    This fixture:
    - forces persistent cache usage
    - runs build_index exactly once
    - mirrors Docker startup behavior
    """

    cache_dir = os.environ.get("KNOWLEDGE_CACHE_DIR", "/data/knowledge_cache")
    os.environ["KNOWLEDGE_CACHE_DIR"] = cache_dir
    os.environ["FORCE_REBUILD_INDEX"] = "1"

    # Import locally to avoid side effects during collection
    from backend.app.knowledge.build.build_index import main as build_main

    build_main()

