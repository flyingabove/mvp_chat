from unittest.mock import patch

from backend.app.engine.story_loader import load_story, StoryDefinition
from tests.conftest import first_story_id

STORY_ID = first_story_id()


def test_load_story_returns_definition_for_existing_story():
    story = load_story(STORY_ID)
    assert story is not None
    assert hasattr(story, "characters")
    assert story.characters  # normalized list

    story_dict = story.as_dict()
    # Basic sanity: required keys in your story format
    assert story_dict.get("title")
    assert "opening" in story_dict


def test_load_story_returns_none_for_missing_story():
    assert load_story("does_not_exist") is None


def test_story_loader_parses_relationships():
    """Stories with a relationships section get a CharacterGraph."""
    story = load_story(STORY_ID)
    assert story is not None
    assert story.relationships is not None
    assert len(story.relationships.edges) > 0


def test_story_loader_character_graph_has_edges():
    """Relationship edges have from_id, to_id, and state."""
    story = load_story(STORY_ID)
    assert story.relationships is not None
    for edge in story.relationships.edges.values():
        assert edge.from_id
        assert edge.to_id
        assert edge.state is not None


# ─── BUG-13: story_loader warns when no is_main character found ──────────────

def test_story_loader_warns_when_no_is_main_flag(capfd):
    """BUG-13: StoryDefinition.from_dict should jlog a warning when defaulting is_main."""
    data = {
        "id": "test_story",
        "title": "Test",
        "characters": [
            {"key": "alice", "name": "Alice", "role": "npc"},  # no is_main: true
            {"key": "bob", "name": "Bob", "role": "npc"},
        ],
    }
    logged = []
    with patch("backend.app.engine.story_loader.jlog") as mock_jlog:
        story = StoryDefinition.from_dict(data)
        # Should have called jlog with a warning
        warning_calls = [
            c for c in mock_jlog.call_args_list
            if c.args and isinstance(c.args[0], dict) and c.args[0].get("kind") == "story_warning"
        ]
        assert len(warning_calls) >= 1
    # First character should get is_main = True
    assert story.characters[0].is_main is True


def test_story_loader_no_warning_when_is_main_present():
    """BUG-13: No warning is emitted when is_main is explicitly set."""
    data = {
        "id": "test_story",
        "title": "Test",
        "characters": [
            {"key": "alice", "name": "Alice", "role": "ghost", "is_main": True},
            {"key": "bob", "name": "Bob", "role": "npc"},
        ],
    }
    with patch("backend.app.engine.story_loader.jlog") as mock_jlog:
        story = StoryDefinition.from_dict(data)
        warning_calls = [
            c for c in mock_jlog.call_args_list
            if c.args and isinstance(c.args[0], dict) and c.args[0].get("kind") == "story_warning"
        ]
        assert len(warning_calls) == 0
    assert story.characters[0].is_main is True