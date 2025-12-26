from fastapi import APIRouter, HTTPException
from backend.app.engine.story_loader import load_story

router = APIRouter()

@router.get("/story/{story_id}")
def get_story_meta(story_id: str):
    try:
        story = load_story(story_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Story not found")

    goal = story.get("goal", {}) or {}
    rules = story.get("rules", {}) or {}

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
        }
    }
