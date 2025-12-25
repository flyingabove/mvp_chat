# backend/app/knowledge/build/ensure_indexes.py
from __future__ import annotations

import sys
from .build_index import main as build_main

print("🧠 ensure_indexes → invoking build_index.main()")


def main():
    try:
        build_main()
    except Exception as e:
        print("❌ ensure_indexes failed:", repr(e))
        raise

if __name__ == "__main__":
    main()
