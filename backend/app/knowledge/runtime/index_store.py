# backend/app/knowledge/runtime/index_store.py

from __future__ import annotations

import threading
from typing import Dict, Any, Optional

from app.knowledge.runtime.load_indexes import load_character_indexes

_INDEXES: Optional[Dict[str, Any]] = None
_LOCK = threading.Lock()


def reset_indexes_for_tests() -> None:
    global _INDEXES
    with _LOCK:
        _INDEXES = None


def get_indexes(character_id: str = "1_iu") -> Dict[str, Any]:
    global _INDEXES
    if _INDEXES is None:
        with _LOCK:
            if _INDEXES is None:
                _INDEXES = load_character_indexes(character_id)
    return _INDEXES
