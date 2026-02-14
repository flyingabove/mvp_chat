import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from backend.app.engine.story_loader import load_story, find_story_dir
from backend.app.engine.world.world_loader import WorldLoader

router = APIRouter()

# Absolute path to stories directory (used by image endpoint)
_STORIES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stories")


def _sanitize_path(rel_path: str) -> str | None:
    """Normalize and reject traversal in map image paths."""
    if not rel_path:
        return None
    safe = os.path.normpath(rel_path)
    if ".." in safe or safe.startswith(os.sep):
        return None
    return safe


def _discover_map_image(story_id: str, story_world_cfg: dict | None = None) -> str | None:
    """Find a map image either from story config or conventional naming."""
    # First: explicit path from story world config (e.g., world_map_image)
    world_cfg = story_world_cfg or {}
    explicit = _sanitize_path(str(world_cfg.get("world_map_image", "")).strip())
    if explicit:
        candidate = os.path.join(_STORIES_DIR, explicit)
        if os.path.isfile(candidate):
            return explicit

    # Second: conventional naming {folder}/{folder}.png
    subdir = find_story_dir(story_id)
    if not subdir:
        return None
    candidate = os.path.join(_STORIES_DIR, subdir, f"{subdir}.png")
    if os.path.isfile(candidate):
        return f"{subdir}/{subdir}.png"

    # Third: common alternates tied to story_id naming
    for alt in (f"{story_id}.png", f"{story_id}_wm.png"):
        candidate = os.path.join(_STORIES_DIR, subdir, alt)
        if os.path.isfile(candidate):
            return f"{subdir}/{alt}"
    return None


@router.get("/story-image/{path:path}")
def get_story_image(path: str):
    """Serve story image files (PNG only) from backend/app/stories/."""
    if not path.endswith(".png"):
        raise HTTPException(status_code=400, detail="Only PNG files are served")

    # Prevent path traversal
    safe = os.path.normpath(path)
    if ".." in safe or safe.startswith(os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")

    full = os.path.join(_STORIES_DIR, safe)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(full, media_type="image/png")


@router.get("/story/{story_id}")
def get_story_meta(story_id: str):
    try:
        story = load_story(story_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Story not found")

    goal = story.get("goal", {}) or {}
    rules = story.get("rules", {}) or {}

    # Load known locations from world if available
    known_locations = []
    world_cfg = story.get("world", {}) or {}
    seed = int(world_cfg.get("seed", 0))
    world_file = str(world_cfg.get("file", "")).strip()

    try:
        if world_file:
            loaded = WorldLoader.load_from_file(f"backend/app/stories/{world_file}", seed=seed)
        else:
            # Try auto-loading from story_id
            loaded = WorldLoader.try_load_story_world(story_id, stories_dir="backend/app/stories", seed=seed)

        if loaded and loaded.world_graph:
            for loc_id, loc in loaded.world_graph.locations.items():
                known_locations.append({
                    "id": loc_id,
                    "name": getattr(loc, "name", ""),
                    "description": getattr(loc, "description", ""),
                    "tags": getattr(loc, "tags", [])
                })
    except Exception:
        # Silently fail if world loading fails
        pass

    # Auto-discover map image by convention ({folder}/{folder}.png)
    world_map_image = _discover_map_image(story_id, world_cfg)

    result = {
        "id": story_id,
        "title": story.get("title", story_id),
        "goal": {
            "win_text_rule": goal.get("win_text_rule", "")
        },
        "rules": {
            "player_role": rules.get("player_role", ""),
            "mode": rules.get("mode", ""),
            "pacing": rules.get("pacing", ""),
            "turn_structure": rules.get("turn_structure", ""),
            "win_condition": rules.get("win_condition", ""),
            "loss_condition": rules.get("loss_condition", ""),
            "dialogue": rules.get("dialogue", ""),
        },
        "known_locations": known_locations,
    }
    if world_map_image:
        result["world_map_image"] = world_map_image
        try:
            from PIL import Image
            with Image.open(os.path.join(_STORIES_DIR, world_map_image)) as im:
                result["world_map_image_size"] = {"w": im.width, "h": im.height}
        except Exception:
            pass
    return result
