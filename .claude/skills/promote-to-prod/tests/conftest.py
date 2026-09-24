"""Skill tests run outside the repo's tests/ tree (never in the Docker build
gate - the arena is local-only tooling). Make `arena` and `backend` importable."""
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = next(p for p in SKILL_DIR.parents if (p / "backend" / "app" / "main.py").exists())
for path in (str(SKILL_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
