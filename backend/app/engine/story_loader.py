# app/engine/story_loader.py
import json
import os


def load_story(story_id: str) -> dict:
    """
    Load a story JSON file by id from app/stories/<story_id>.json or app/stories/<subdirectory>/<story_id>.json,
    handling BOM and logging basic debug info.
    """
    base = os.path.dirname(os.path.dirname(__file__))  # app/
    stories_dir = os.path.join(base, "stories")
    
    # Try direct path first: app/stories/<story_id>.json
    story_path = os.path.join(stories_dir, f"{story_id}.json")

    print("DEBUG story_path:", story_path)
    print("DEBUG exists:", os.path.isfile(story_path))
    
    # If not found, try subdirectories (e.g., app/stories/1_iu/<story_id>.json)
    if not os.path.isfile(story_path):
        try:
            subdirs = [d for d in os.listdir(stories_dir) 
                      if os.path.isdir(os.path.join(stories_dir, d)) and not d.startswith("__")]
            for subdir in subdirs:
                alt_path = os.path.join(stories_dir, subdir, f"{story_id}.json")
                if os.path.isfile(alt_path):
                    story_path = alt_path
                    print("DEBUG: Found story in subdirectory:", subdir)
                    break
        except Exception as e:
            print("ERROR scanning story subdirectories:", e)
    
    try:
        print("DEBUG listdir stories:", os.listdir(stories_dir))
    except Exception as e:
        print("ERROR listing stories directory:", e)

    if not os.path.isfile(story_path):
        print("ERROR: Story file does not exist:", story_path)
        return {}

    try:
        # Read raw text first so we can strip BOM
        with open(story_path, "r", encoding="utf-8") as f:
            raw = f.read()

        # Strip Byte Order Mark (common cause of silent JSON failure)
        if raw.startswith("\ufeff"):
            print("DEBUG: Stripped BOM from story file")
            raw = raw.lstrip("\ufeff")

        return json.loads(raw)

    except json.JSONDecodeError as e:
        print("JSON ERROR:", e)
        print("Story file is not valid JSON:", story_path)
        return {}

    except Exception as e:
        print("UNEXPECTED ERROR loading story:", e)
        return {}
