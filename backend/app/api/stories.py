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
    Stories can be in backend/app/stories/ directly or in subdirectories.
    """
    stories_path = _stories_dir()
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
        out.append({"id": sid, "title": title, "theme": theme})

    return {"stories": out}


def _find_story_file(story_id: str) -> Path | None:
    """Locate the story JSON file for a given story_id."""
    stories_path = _stories_dir()
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
async def story_context(story_id: str):
    """Return scoring-relevant context for a story.

    The scorer/grader needs story canon to properly evaluate NPC responses.
    This endpoint extracts the key sections without exposing the full config.
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
