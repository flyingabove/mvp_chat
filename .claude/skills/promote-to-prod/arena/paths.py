# .claude/skills/promote-to-prod/arena/paths.py
"""Where things are. The arena lives in the promote-to-prod skill folder
(local-only tooling, never deployed) and imports the game's own modules from
the repository root."""
from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "backend" / "app" / "main.py").exists():
            return candidate
    raise RuntimeError("could not find the StoriesChat repository root above " + str(here))


REPO_ROOT = find_repo_root()
SKILL_DIR = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO_ROOT / "data" / "eval_arena"          # gitignored
