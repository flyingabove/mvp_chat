import json
import re
from pathlib import Path
from unittest.mock import patch

from backend.app.engine.story_loader import load_story, StoryDefinition, STORIES_DIR
from backend.app.engine.world.world_loader import WorldLoader
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
    """The original six each retain their own identity through normalization."""
    story = load_story("six_strangers")
    assert story is not None
    assert len(story.characters) == 6

    seen_texts = []
    for char in story.characters:
        assert char.self_knowledge, f"{char.key} is missing self_knowledge"
        assert len(char.self_knowledge) >= 2
        joined = " ".join(char.self_knowledge)
        assert joined not in seen_texts, f"{char.key}'s self_knowledge duplicates another character's"
        seen_texts.append(joined)

    keys = {c.key for c in story.characters}
    assert keys == {"makoto", "minori", "yuki", "mizuki", "uchi", "yuriko"}
    assert [c.key for c in story.characters if c.is_main] == ["mizuki"]


def test_six_strangers_content_references_and_private_concerns_are_consistent():
    """Renaming the cast must update every knowledge and relationship reference."""
    story = load_story("six_strangers")
    cfg = story.as_dict()
    keys = {c.key for c in story.characters}
    participants = keys | {"player"}
    visibility_keys = participants | {"all_characters"}
    facts = cfg["epistemic_seed"]["canonical_facts"]
    assert len({fact["id"] for fact in facts}) == len(facts)
    for fact in facts:
        assert (fact.get("content") or fact.get("text") or "").strip()
        assert fact["confidence"] == 1.0
        for field in ("known_by", "not_known_by", "maybe_known_by"):
            assert set(fact[field]) <= visibility_keys
        assert not set(fact["known_by"]) & set(fact["not_known_by"])
    by_id = {fact["id"]: fact for fact in facts}
    for key in keys:
        private = by_id[f"{key}_private_concern"]
        assert private["known_by"] == [key]
        assert set(private["not_known_by"]) == participants - {key}
        assert private["maybe_known_by"] == []

    beliefs = cfg["epistemic_seed"]["belief_seeds"]
    assert set(beliefs) == keys
    for claims in beliefs.values():
        for claim in claims:
            for field in ("known_by", "not_known_by", "maybe_known_by"):
                assert set(claim.get(field, [])) <= visibility_keys
    edges = cfg["relationships"]["edges"]
    pairs = [(edge["from"], edge["to"]) for edge in edges]
    assert len(pairs) == len(set(pairs)), "Duplicate directed edges overwrite each other"
    for edge in edges:
        assert edge["from"] in participants
        assert edge["to"] in participants
        assert edge["from"] != edge["to"]
        assert not edge.get("prior_relationship", False)
        assert not edge.get("prior_intimacy", False)
        assert not edge.get("in_relationship", False)
    assert {(key, "player") for key in keys} <= set(pairs)
    assert any(source in keys and target in keys for source, target in pairs)

    opening = cfg["opening"]["text"]
    assert "\n\n" in opening
    assert "\\n" not in opening, "Opening paragraphs must use actual newlines"
    content = json.dumps(cfg, ensure_ascii=False)
    assert not re.search(r"\b(?:kenji|reiko|asami|ren|nishi-kaede)\b", content, re.I)
    assert cfg["mode"]["type"] == "social_sim"
    assert cfg["mode"]["cast_size"] == len(keys)
    assert cfg["mode"]["open_ended"] is True
    assert "goal" not in cfg and "win_detection" not in cfg


def test_six_strangers_world_supports_return_travel_and_all_starting_characters():
    """Inspect authored edges directly: route resolution hides islands with fallback edges."""
    story = load_story("six_strangers")
    world_cfg = story.as_dict()["world"]
    world_path = Path(STORIES_DIR) / world_cfg["file"]
    loaded = WorldLoader.load_from_file(str(world_path), story_id="six_strangers")
    graph = loaded.world_graph
    locations = set(graph.locations)
    assert world_cfg["start_location_id"] == "front_entry"
    starts = world_cfg["character_start_locations"]
    assert starts == {
        "makoto": "living_room", "minori": "living_room", "yuki": "dining_room",
        "mizuki": "front_entry", "uchi": "boys_bedroom", "yuriko": "girls_bedroom",
    }
    assert set(starts.values()) <= locations
    assert {"boys_bedroom", "girls_bedroom", "player_bedroom", "terrace", "gotanda_station"} <= locations
    for start in locations:
        visited = {start}
        pending = [start]
        while pending:
            for edge in graph.get_outgoing(pending.pop()).to_tuple():
                assert edge.minutes > 0
                assert edge.to_id.value in locations
                if not edge.blocked and edge.to_id.value not in visited:
                    visited.add(edge.to_id.value)
                    pending.append(edge.to_id.value)
        assert visited == locations, f"Cannot travel from {start} to {locations - visited}"
    world_text = world_path.read_text(encoding="utf-8")
    assert not re.search(r"\b(?:kenji|reiko|asami|ren|nishi-kaede)\b", world_text, re.I)
