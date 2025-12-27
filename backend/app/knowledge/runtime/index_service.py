from threading import Lock
from typing import Optional

from backend.app.knowledge.contracts.index_bundle import CharacterIndexBundle
from backend.app.knowledge.runtime.load_indexes import load_character_indexes

class IndexService:
    _lock = Lock()
    _bundle: Optional[CharacterIndexBundle] = None

    @classmethod
    def get(cls, character_id: str = "1_iu") -> CharacterIndexBundle:
        if cls._bundle is None:
            with cls._lock:
                if cls._bundle is None:
                    cls._bundle = load_character_indexes(character_id)
        return cls._bundle

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._lock:
            cls._bundle = None
