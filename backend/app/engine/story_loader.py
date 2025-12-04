import json
import os

def load_story(story_id: str) -> dict:

    base = os.path.dirname(os.path.dirname(__file__))  # app/
    story_path = os.path.join(base, "stories", f"{story_id}.json")
    print("DEBUG story_path:", story_path)
    print("DEBUG exists:", os.path.isfile(story_path))
    print("DEBUG listdir stories:", os.listdir(os.path.join(base, "stories")))

    if not os.path.isfile(story_path):
        return {}
    with open(story_path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

