from __future__ import annotations

import os
from threading import Lock
from typing import Dict, Optional

from backend.app.knowledge.contracts.index_bundle import CharacterIndexBundle
from backend.app.knowledge.runtime.load_indexes import load_character_indexes


class IndexService:
    """Thread-safe cache for loaded retrieval index bundles.

    This service supports multiple character bundles (one per character_id)
    and lets the API route retrieval per active game session.

    The active character id may be set per request using set_active_character().
    If no active id is configured, get() will raise with a clear error.
    """

    _lock = Lock()
    _bundles: Dict[str, CharacterIndexBundle] = {}
    _active_character_id: str = ""

    @classmethod
    def set_active_character(cls, character_id: str) -> None:
        """Set the default character bundle used by get() when none is passed."""
        cls._active_character_id = (character_id or "").strip()

    @classmethod
    def get_active_character(cls) -> str:
        # Environment fallback (useful for single-character deployments)
        if cls._active_character_id:
            return cls._active_character_id
        env = (os.getenv("KNOWLEDGE_CHARACTER_ID") or "").strip()
        if env:
            return env

        # Last-resort fallback: if there is exactly one character dir packaged,
        # use it. This keeps local tests/dev ergonomic without hardcoding a persona.
        try:
            from pathlib import Path
            knowledge_dir = Path(__file__).resolve().parents[1] / "characters"
            dirs = [p.name for p in knowledge_dir.iterdir() if p.is_dir()]
            if len(dirs) == 1:
                return dirs[0]
        except Exception:
            pass
        return ""

    @classmethod
    def get(cls, character_id: Optional[str] = None) -> CharacterIndexBundle:
        cid = (character_id or cls.get_active_character()).strip()
        if not cid:
            raise RuntimeError(
                "No knowledge character id configured. "
                "Set state.knowledge_character_id from the story config, "
                "or set env KNOWLEDGE_CHARACTER_ID."
            )

        if cid in cls._bundles:
            return cls._bundles[cid]

        with cls._lock:
            if cid in cls._bundles:
                return cls._bundles[cid]
            cls._bundles[cid] = load_character_indexes(cid)
            return cls._bundles[cid]

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._lock:
            cls._bundles = {}
            cls._active_character_id = ""
