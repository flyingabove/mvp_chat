# app/engine/story_loader.py
import json
import os

from backend.app.utils.logging_utils import jlog


def _story_json_candidates(story_id: str) -> list[str]:
    """Filenames to try when resolving a story (handles _story suffix convention)."""
    return [f"{story_id}.json", f"{story_id}_story.json"]


def find_story_dir(story_id: str) -> str | None:
    """
    Return the subdirectory name (e.g. '1_iu_murder_mystery') that contains
    the story JSON for story_id, or None if it lives at root / not found.
    """
    base = os.path.dirname(os.path.dirname(__file__))  # app/
    stories_dir = os.path.join(base, "stories")

    # Direct path (root level)
    for fname in _story_json_candidates(story_id):
        if os.path.isfile(os.path.join(stories_dir, fname)):
            return None

    try:
        for d in os.listdir(stories_dir):
            if os.path.isdir(os.path.join(stories_dir, d)) and not d.startswith("__"):
                for fname in _story_json_candidates(story_id):
                    if os.path.isfile(os.path.join(stories_dir, d, fname)):
                        return d
    except Exception:
        pass
    return None


def load_story(story_id: str) -> dict:
    """
    Load a story JSON file by id, trying both {story_id}.json and
    {story_id}_story.json in root and subdirectories.
    """
    base = os.path.dirname(os.path.dirname(__file__))  # app/
    stories_dir = os.path.join(base, "stories")

    story_path = None

    # Try root level first
    for fname in _story_json_candidates(story_id):
        candidate = os.path.join(stories_dir, fname)
        if os.path.isfile(candidate):
            story_path = candidate
            break

    jlog({"kind": "story_load_attempt", "story_id": story_id,
          "path": story_path or os.path.join(stories_dir, f"{story_id}.json"),
          "exists": story_path is not None})

    # If not found at root, try subdirectories
    if not story_path:
        try:
            subdirs = [d for d in os.listdir(stories_dir)
                      if os.path.isdir(os.path.join(stories_dir, d)) and not d.startswith("__")]
            for subdir in subdirs:
                for fname in _story_json_candidates(story_id):
                    alt_path = os.path.join(stories_dir, subdir, fname)
                    if os.path.isfile(alt_path):
                        story_path = alt_path
                        jlog({"kind": "story_found_in_subdir", "story_id": story_id, "subdir": subdir})
                        break
                if story_path:
                    break
        except Exception as e:
            jlog({"kind": "story_subdir_scan_error", "story_id": story_id, "error": str(e)})

    if not story_path:
        jlog({"kind": "story_not_found", "story_id": story_id})
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
