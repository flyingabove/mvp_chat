from backend.app.engine.story_loader import load_story
from tests.conftest import first_story_id

STORY_ID = first_story_id()


def test_load_story_returns_dict_for_existing_story():
    story = load_story(STORY_ID)
    assert isinstance(story, dict)
    # Basic sanity: required keys in your story format
    assert story.get("title")
    assert "opening" in story


def test_load_story_returns_empty_for_missing_story():
    assert load_story("does_not_exist") == {}