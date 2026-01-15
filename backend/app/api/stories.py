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
    """
    stories_path = _stories_dir()
    out = []
    if not stories_path.exists():
        return {"stories": out}

    for p in sorted(stories_path.glob("*.json")):
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
