import json
import os

def load_story(story_id: str) -> dict:
    base = os.path.dirname(os.path.dirname(__file__))  # app/
    story_path = os.path.join(base, "stories", f"{story_id}.json")

    print("DEBUG story_path:", story_path)
    print("DEBUG exists:", os.path.isfile(story_path))
    print("DEBUG listdir stories:", os.listdir(os.path.join(base, "stories")))

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
