"""Game arena CLI - local-only tooling of the promote-to-prod skill.

Run from anywhere with the storieschat conda env:
    python .claude/skills/promote-to-prod/arena_cli.py precheck
    python .claude/skills/promote-to-prod/arena_cli.py all --profile gate --judges jev llm ollama

See SKILL.md in this folder for the release procedure.
"""
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
REPO_ROOT = next(p for p in SKILL_DIR.parents if (p / "backend" / "app" / "main.py").exists())
sys.path[:0] = [str(SKILL_DIR), str(REPO_ROOT)]      # `arena` package + the game's `backend` package

from arena.cli import main  # noqa: E402

if __name__ == "__main__":
    main(sys.argv[1:])
