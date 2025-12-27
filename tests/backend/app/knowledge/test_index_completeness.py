import importlib
import os
from pathlib import Path


def test_build_index_has_no_import_time_side_effects(tmp_path, monkeypatch):
    """
    build_index.py should not create any /data or cache directories at import time.
    """
    cache_root = tmp_path / "knowledge_cache"
    monkeypatch.setenv("KNOWLEDGE_CACHE_DIR", str(cache_root))
    monkeypatch.setenv("FORCE_REBUILD_INDEX", "0")

    modname = "backend.app.knowledge.build.build_index"

    if modname in importlib.sys.modules:
        del importlib.sys.modules[modname]

    importlib.import_module(modname)

    # Import should not create cache directories.
    assert not cache_root.exists(), "Importing build_index should not create cache dirs"
