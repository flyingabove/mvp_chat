from fastapi import APIRouter, HTTPException
from backend.app.engine.story_loader import load_story
from backend.app.engine.world.world_loader import WorldLoader

router = APIRouter()

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

    return {
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
        "known_locations": known_locations
    }
