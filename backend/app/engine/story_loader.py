# app/engine/story_loader.py
import json
import os

from backend.app.utils.logging_utils import jlog


def find_story_dir(story_id: str) -> str | None:
    """
    Return the subdirectory name (e.g. '1_iu') that contains story_id.json,
    or None if the story lives at the root or is not found.
    """
    base = os.path.dirname(os.path.dirname(__file__))  # app/
    stories_dir = os.path.join(base, "stories")

    # Direct path (root level)
    if os.path.isfile(os.path.join(stories_dir, f"{story_id}.json")):
        return None

    try:
        for d in os.listdir(stories_dir):
            if os.path.isdir(os.path.join(stories_dir, d)) and not d.startswith("__"):
                if os.path.isfile(os.path.join(stories_dir, d, f"{story_id}.json")):
                    return d
    except Exception:
        pass
    return None


def load_story(story_id: str) -> dict:
    """
    Load a story JSON file by id from app/stories/<story_id>.json or app/stories/<subdirectory>/<story_id>.json,
    handling BOM and logging basic debug info.
    """
    base = os.path.dirname(os.path.dirname(__file__))  # app/
    stories_dir = os.path.join(base, "stories")

    # Try direct path first: app/stories/<story_id>.json
    story_path = os.path.join(stories_dir, f"{story_id}.json")

    jlog({"kind": "story_load_attempt", "story_id": story_id, "path": story_path, "exists": os.path.isfile(story_path)})

    # If not found, try subdirectories (e.g., app/stories/1_iu/<story_id>.json)
    if not os.path.isfile(story_path):
        try:
            subdirs = [d for d in os.listdir(stories_dir)
                      if os.path.isdir(os.path.join(stories_dir, d)) and not d.startswith("__")]
            for subdir in subdirs:
                alt_path = os.path.join(stories_dir, subdir, f"{story_id}.json")
                if os.path.isfile(alt_path):
                    story_path = alt_path
                    jlog({"kind": "story_found_in_subdir", "story_id": story_id, "subdir": subdir})
                    break
        except Exception as e:
            jlog({"kind": "story_subdir_scan_error", "story_id": story_id, "error": str(e)})

    if not os.path.isfile(story_path):
        jlog({"kind": "story_not_found", "story_id": story_id, "path": story_path})
        return {}

    try:
        # Read raw text first so we can strip BOM
        with open(story_path, "r", encoding="utf-8") as f:
            raw = f.read()

        # Strip Byte Order Mark (common cause of silent JSON failure)
        if raw.startswith("\ufeff"):
            jlog({"kind": "story_bom_stripped", "story_id": story_id})
            raw = raw.lstrip("\ufeff")

        return json.loads(raw)

    except json.JSONDecodeError as e:
        jlog({"kind": "story_json_error", "story_id": story_id, "error": str(e), "path": story_path})
        return {}

    except Exception as e:
        jlog({"kind": "story_load_error", "story_id": story_id, "error": str(e)})
        return {}
