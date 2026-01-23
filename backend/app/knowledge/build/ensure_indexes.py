# backend/app/knowledge/build/ensure_indexes.py
from __future__ import annotations

import sys
import os
from .build_index import main as build_main

print("🧠 ensure_indexes → invoking build_index.main()")


def main(character_dirname: str | None = None):
    """
    Ensure indexes are built for a character.
    
    Args:
        character_dirname: Directory name under knowledge/characters/ (e.g., "1_iu", "2_alice")
                          If None, uses CHARACTER_DIRNAME env var or defaults to "1_iu".
    """
    if character_dirname is None:
        character_dirname = os.getenv("CHARACTER_DIRNAME", "1_iu")

    try:
        build_main(character_dirname)
    except Exception as e:
        print("❌ ensure_indexes failed:", repr(e))
        raise

if __name__ == "__main__":
    # Support optional command-line argument
    character_dirname = sys.argv[1] if len(sys.argv) > 1 else None
    main(character_dirname)
