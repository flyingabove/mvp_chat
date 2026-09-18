from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json
import re
import uuid

from backend.app.auth.dependencies import require_operator
from backend.app.engine.story_loader import STORIES_DIR

router = APIRouter()


class StoryDraftRequest(BaseModel):
    title: str
    genre: str
    description: str


@router.get("/stories")
async def list_stories():
    """Return a list of available story configs.

    This endpoint enables the frontend to build a dynamic menu so new
    game modes / characters can be added by dropping in a new story JSON.
    Stories can be in backend/app/stories/ directly or in subdirectories.
    """
    stories_path = Path(STORIES_DIR)
    out = []
    if not stories_path.exists():
        return {"stories": out}

    # Collect story files from both root and subdirectories
    story_files = []
    
    # Root level stories
    story_files.extend(sorted(stories_path.glob("*.json")))
    
    # Subdirectory stories (e.g., <int>_<slug>/*, etc.)
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
        genre = str(cfg.get("genre") or theme or "").strip()
        description = str(cfg.get("description") or "").strip()
        thumbnail_url = cfg.get("thumbnail_url") or None
        featured = bool(cfg.get("featured", False))
        out.append({
            "id": sid,
            "title": title,
            "theme": theme,
            "genre": genre,
            "description": description,
            "thumbnail_url": thumbnail_url,
            "featured": featured,
        })

    return {"stories": out}


def _find_story_file(story_id: str) -> Path | None:
    """Locate the story JSON file for a given story_id."""
    stories_path = Path(STORIES_DIR)
    if not stories_path.exists():
        return None

    # Check root-level files
    for p in stories_path.glob("*.json"):
        if p.name.endswith("_world.json"):
            continue
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
            if str(cfg.get("id") or p.stem).strip() == story_id:
                return p
        except Exception:
            continue

    # Check subdirectories
    for subdir in sorted(stories_path.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith("__"):
            for p in subdir.glob("*.json"):
                if p.name.endswith("_world.json"):
                    continue
                try:
                    cfg = json.loads(p.read_text(encoding="utf-8"))
                    if str(cfg.get("id") or p.stem).strip() == story_id:
                        return p
                except Exception:
                    continue
    return None


@router.get("/stories/{story_id}/context")
async def story_context(story_id: str, _op: dict = Depends(require_operator)):
    """Return scoring-relevant context for a story.

    The scorer/grader needs story canon to properly evaluate NPC responses.
    This endpoint extracts the key sections without exposing the full config.

    A03: this returns canonical_facts (answers), so it must stay
    operator-only — never reachable by ordinary players.
    """
    p = _find_story_file(story_id)
    if not p:
        return {"error": "Story not found", "story_id": story_id}

    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "Failed to parse story JSON"}

    # Extract scoring-relevant sections
    epistemic = cfg.get("epistemic_seed") or {}
    canonical_facts = epistemic.get("canonical_facts") or []

    characters = []
    for ch in cfg.get("characters") or []:
        characters.append({
            "key": ch.get("key", ""),
            "name": ch.get("name", ""),
            "role": ch.get("role", ""),
            "is_main": ch.get("is_main", False),
            "is_suspect": ch.get("is_suspect", False),
            "tags": ch.get("tags", []),
        })

    protagonist = cfg.get("protagonist") or {}

    return {
        "story_id": story_id,
        "title": cfg.get("title", ""),
        "character_self_knowledge": cfg.get("character_self_knowledge") or [],
        "canonical_facts": [
            {"id": f.get("id", ""), "text": f.get("text") or f.get("content", ""), "known_by": f.get("known_by", [])}
            for f in canonical_facts
        ],
        "characters": characters,
        "protagonist": {
            "name": protagonist.get("name", ""),
            "role": protagonist.get("role", ""),
            "personality": protagonist.get("personality", ""),
        },
        "rules": cfg.get("rules") or {},
    }


@router.post("/stories/draft")
async def create_story_draft(req: StoryDraftRequest, _op: dict = Depends(require_operator)):
    """Create a minimal stub story JSON for a new draft game.

    Saves a skeleton story JSON to backend/app/stories/ so it shows up in
    the story list and can be further developed.

    A03: this is a content-authoring mutation and must stay operator-only.
    """
    title = req.title.strip()
    genre = req.genre.strip()
    description = req.description.strip()

    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if len(title) > 100:
        raise HTTPException(status_code=400, detail="title too long (max 100 chars)")
    if len(description) > 500:
        raise HTTPException(status_code=400, detail="description too long (max 500 chars)")

    # Generate a URL-safe ID from the title
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40]
    short_id = uuid.uuid4().hex[:6]
    story_id = f"draft_{slug}_{short_id}"

    stub = {
        "id": story_id,
        "title": title,
        "theme": genre.lower().replace(" ", "_"),
        "genre": genre,
        "description": description,
        "thumbnail_url": None,
        "featured": False,
        "meta": {"draft": True},
        "characters": [],
        "protagonist": {"role": "Player", "profile": ""},
        "rules": {},
        "goal": {"win_text_rule": ""},
        "opening": "",
    }

    stories_dir = Path(STORIES_DIR)
    out_path = stories_dir / f"{story_id}_story.json"
    try:
        out_path.write_text(json.dumps(stub, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save story: {e}")

    return {"id": story_id, "title": title}
