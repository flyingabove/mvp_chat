from __future__ import annotations

from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter()


def _stories_dir() -> Path:
    # Backend ships stories in backend/app/stories
    return Path(__file__).resolve().parents[1] / "stories"


@router.get("/stories")
async def list_stories():
    """Return a list of available story configs.

    This endpoint enables the frontend to build a dynamic menu so new
    game modes / characters can be added by dropping in a new story JSON.
    Stories can be in backend/app/stories/ directly or in subdirectories like backend/app/stories/1_iu/
    """
    stories_path = _stories_dir()
    out = []
    if not stories_path.exists():
        return {"stories": out}

    # Collect story files from both root and subdirectories
    story_files = []
    
    # Root level stories
    story_files.extend(sorted(stories_path.glob("*.json")))
    
    # Subdirectory stories (e.g., 1_iu/*, 2_other/*, etc.)
    for subdir in sorted(stories_path.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith("__"):
            story_files.extend(sorted(subdir.glob("*.json")))
    
    for p in story_files:
        # Skip world graph sidecar files.
        if p.name.endswith("_world.json"):
            continue
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        sid = str(cfg.get("id") or p.stem).strip()
        title = str(cfg.get("title") or sid).strip()
        theme = str(cfg.get("theme") or "").strip()
        out.append({"id": sid, "title": title, "theme": theme})

    return {"stories": out}
