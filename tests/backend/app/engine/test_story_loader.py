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

# --- BL-07: per-character self_knowledge survives StoryDefinition normalization --

def test_story_definition_preserves_per_character_self_knowledge_round_trip():
    """StoryDefinition.from_dict calls Character.from_dict then c.to_dict() to
    build normalized["characters"] -- both ends must agree on the key or a
    per-character self_knowledge array silently vanishes on this round-trip."""
    data = {
        "id": "test_story_self_knowledge",
        "title": "Test",
        "characters": [
            {
                "key": "alice",
                "name": "Alice",
                "role": "npc",
                "is_main": True,
                "self_knowledge": ["You are the focal character."],
            },
            {
                "key": "bob",
                "name": "Bob",
                "role": "npc",
                "self_knowledge": ["You are quietly resentful.", "You never forget a slight."],
            },
            {
                "key": "carol",
                "name": "Carol",
                "role": "npc",
                # No self_knowledge -- must remain empty, not inherit anyone else's.
            },
        ],
    }
    story = StoryDefinition.from_dict(data)
    by_key = {c.key: c for c in story.characters}
    assert by_key["alice"].self_knowledge == ["You are the focal character."]
    assert by_key["bob"].self_knowledge == [
        "You are quietly resentful.",
        "You never forget a slight.",
    ]
    assert by_key["carol"].self_knowledge == []

    # And the normalized as_dict() form (normalized["characters"] = [c.to_dict() ...])
    # also carries it, since that's what downstream consumers (prompt_engine) read.
    story_dict = story.as_dict()
    chars_by_key = {c["key"]: c for c in story_dict["characters"]}
    assert chars_by_key["bob"]["self_knowledge"] == [
        "You are quietly resentful.",
        "You never forget a slight.",
    ]


def test_six_strangers_all_characters_have_distinct_self_knowledge():
    """Six Strangers ships four housemates and, per BL-07 (self_knowledge is
    genuinely per-character now), every one of them must author their own
    non-empty self_knowledge array — no falling back to a single main
    character's block. Each array must also be distinct from the others."""
    story = load_story("six_strangers")
    assert story is not None
    assert len(story.characters) == 4

    seen_texts = []
    for char in story.characters:
        assert char.self_knowledge, f"{char.key} is missing self_knowledge"
        assert len(char.self_knowledge) >= 2
        joined = " ".join(char.self_knowledge)
        assert joined not in seen_texts, f"{char.key}'s self_knowledge duplicates another character's"
        seen_texts.append(joined)

    keys = {c.key for c in story.characters}
    assert keys == {"kenji", "reiko", "asami", "ren"}
