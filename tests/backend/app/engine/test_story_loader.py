from backend.app.engine.story_loader import load_story
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