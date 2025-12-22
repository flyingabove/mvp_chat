import threading
from backend.app.knowledge.runtime.load_indexes import load_character_indexes

_INDEXES = None
_LOCK = threading.Lock()

def get_indexes():
    global _INDEXES
    if _INDEXES is None:
        with _LOCK:
            if _INDEXES is None:  # double-checked locking
                _INDEXES = load_character_indexes()
    return _INDEXES
