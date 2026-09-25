import json
import re
from pathlib import Path
from unittest.mock import patch

from backend.app.engine.story_loader import load_story, StoryDefinition, STORIES_DIR
from backend.app.engine.world.world_loader import WorldLoader
from backend.app.engine.cast_lifecycle import CastLifecycleState, CastStatus
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
    """All 17 authored residents retain distinct identities through normalization."""
    story = load_story("six_strangers")
    assert story is not None
    assert len(story.characters) == 17

    seen_texts = []
    for char in story.characters:
        assert char.self_knowledge, f"{char.key} is missing self_knowledge"
        assert len(char.self_knowledge) >= 2
        joined = " ".join(char.self_knowledge)
        assert joined not in seen_texts, f"{char.key}'s self_knowledge duplicates another character's"
        seen_texts.append(joined)

    keys = {c.key for c in story.characters}
    assert keys == {
        "makoto", "minori", "yuki", "mizuki", "uchi", "yuriko",
        "arman", "arisa", "hikaru", "natsumi", "misaki", "yuto",
        "riko", "momoka", "hayato", "yuuki_byrnes", "masako",
    }
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
    active_keys = {"makoto", "minori", "yuki", "mizuki", "uchi", "yuriko"}
    upcoming_keys = keys - active_keys
    assert {(key, "player") for key in active_keys} <= set(pairs)
    assert not any(
        source in upcoming_keys or target in upcoming_keys
        for source, target in pairs
    ), "Upcoming residents must not leak through seeded relationships"
    assert any(source in keys and target in keys for source, target in pairs)

    variants = cfg["opening"].get("variants") or [cfg["opening"]["text"]]
    opening = "\n".join(variants)
    assert all(len(variant) < 160 for variant in variants)
    assert "\\n" not in opening
    assert "guest room" not in opening.lower()
    content = json.dumps(cfg, ensure_ascii=False)
    assert not re.search(r"\b(?:kenji|reiko|asami|ren|nishi-kaede)\b", content, re.I)
    assert cfg["mode"]["type"] == "social_sim"
    assert cfg["mode"]["cast_size"] == len(active_keys)
    assert cfg["mode"]["open_ended"] is True
    assert "goal" not in cfg and "win_detection" not in cfg


def test_six_strangers_cast_lifecycle_catalog_and_queue_are_consistent():
    """The active six and same-group replacement queues match season entry order."""
    story_path = Path(STORIES_DIR) / "7_six_strangers" / "six_strangers_story.json"
    cfg = json.loads(story_path.read_text(encoding="utf-8"))
    lifecycle = cfg["cast_lifecycle"]
    members = lifecycle["members"]

    assert lifecycle["enabled"] is True
    assert lifecycle["arrival_location_id"] == "front_entry"
    assert lifecycle["replacement_policy"] == "same_slot_next"
    assert lifecycle["departure_policy"] == "committed_intent"
    assert lifecycle["replacement_timing"] == "next_day"
    assert lifecycle["player_mode"] == "resident_slot"
    assert lifecycle["randomize_initial_roster"] is True
    assert lifecycle["slot_groups"] == {
        "men": {"capacity": 3, "label": "Men's resident slots"},
        "women": {"capacity": 3, "label": "Women's resident slots"},
    }
    assert set(members) == {char["key"] for char in cfg["characters"]}

    active = {key for key, value in members.items() if value["initial_status"] == "active"}
    upcoming = {key for key, value in members.items() if value["initial_status"] == "upcoming"}
    assert active == {"makoto", "yuki", "uchi", "minori", "mizuki", "yuriko"}
    assert len(active) == 6
    assert len(upcoming) == 11
    assert sum(members[key]["slot_group"] == "men" for key in active) == 3
    assert sum(members[key]["slot_group"] == "women" for key in active) == 3

    def queue(group):
        return [
            key for key, value in sorted(members.items(), key=lambda item: item[1]["sequence"])
            if value["slot_group"] == group and value["initial_status"] == "upcoming"
        ]

    assert queue("men") == ["arman", "hikaru", "yuto", "hayato", "yuuki_byrnes"]
    assert queue("women") == ["arisa", "natsumi", "misaki", "riko", "momoka", "masako"]
    for group in ("men", "women"):
        sequences = [value["sequence"] for value in members.values() if value["slot_group"] == group]
        assert len(sequences) == len(set(sequences))

    rules = lifecycle["rules_profile"].lower()
    assert "three men and three women" in rules
    assert "two shared cars" in rules
    assert "player and five npc housemates" in rules
    assert "no imposed challenges" in rules
    assert "same-gender replacement" in rules


def test_six_strangers_upcoming_cast_has_private_content_without_fixed_outcomes():
    story_path = Path(STORIES_DIR) / "7_six_strangers" / "six_strangers_story.json"
    cfg = json.loads(story_path.read_text(encoding="utf-8"))
    keys = {char["key"] for char in cfg["characters"]}
    upcoming = {
        key for key, member in cfg["cast_lifecycle"]["members"].items()
        if member["initial_status"] == "upcoming"
    }
    facts = {fact["id"]: fact for fact in cfg["epistemic_seed"]["canonical_facts"]}
    beliefs = cfg["epistemic_seed"]["belief_seeds"]
    by_key = {char["key"]: char for char in cfg["characters"]}

    for key in upcoming:
        assert len(by_key[key]["self_knowledge"]) == 4
        private = facts[f"{key}_private_concern"]
        assert private["known_by"] == [key]
        assert set(private["not_known_by"]) == (keys | {"player"}) - {key}
        assert private["maybe_known_by"] == []
        assert private["confidence"] == 1.0
        assert len(beliefs[key]) == 1
        belief = beliefs[key][0]
        assert belief["source"] == "fictional_first_impression"
        assert belief["known_by"] == [key]
        assert set(belief["not_known_by"]) == (keys | {"player"}) - {key}
        assert belief["maybe_known_by"] == []

    fixed_outcome_phrases = (
        "will fall in love", "will date", "will reject", "will confess",
        "will leave", "must leave", "is destined to", "is fated to",
    )
    authored_future_text = json.dumps(
        {
            "characters": [by_key[key] for key in upcoming],
            "private_facts": [facts[f"{key}_private_concern"] for key in upcoming],
            "beliefs": {key: beliefs[key] for key in upcoming},
        },
        ensure_ascii=False,
    ).lower()
    assert not any(phrase in authored_future_text for phrase in fixed_outcome_phrases)


def test_six_strangers_world_supports_return_travel_and_all_active_starting_characters():
    """Inspect authored edges directly: route resolution hides islands with fallback edges."""
    story = load_story("six_strangers")
    world_cfg = story.as_dict()["world"]
    world_path = Path(STORIES_DIR) / world_cfg["file"]
    loaded = WorldLoader.load_from_file(str(world_path), story_id="six_strangers")
    graph = loaded.world_graph
    locations = set(graph.locations)
    assert world_cfg["start_location_id"] == "front_entry"
    # The roster is random, so there are no per-character premiere starts:
    # the whole opening cast (and the player) gathers for the kitchen dinner.
    assert "character_start_locations" not in world_cfg
    assert story.as_dict()["cast_lifecycle"]["initial_active_location_id"] == "kitchen"
    assert "kitchen" in locations
    assert {"boys_bedroom", "girls_bedroom", "terrace", "gotanda_station"} <= locations
    assert "player_bedroom" not in locations
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


def test_six_strangers_house_holds_exactly_six_residents_with_no_guest_room():
    """The six-resident rule is a hard invariant, not an authoring preference.

    Regression guard for a real cross-agent conflict: the world compiler
    (`scripts/build_six_strangers_world.py`) once generated a `player_bedroom`
    "guest room ... added for the seventh resident", which contradicted the
    `resident_slot` design where the player OCCUPIES one of the six gendered
    slots and shares `boys_bedroom`/`girls_bedroom`. This test pins all three
    facing surfaces together — lifecycle config, slot capacities, and world
    geometry — so regenerating the world can never silently reintroduce a
    seventh resident.
    """
    story = load_story("six_strangers")
    cfg = story.as_dict()
    lifecycle = cfg["cast_lifecycle"]

    # 1. The player takes a slot rather than being an extra arrival.
    assert lifecycle["player_mode"] == "resident_slot"

    # 2. Capacities total exactly six, and the player shares a gendered bedroom.
    capacities = {g: s["capacity"] for g, s in lifecycle["slot_groups"].items()}
    assert capacities == {"men": 3, "women": 3}
    assert sum(capacities.values()) == 6
    assert lifecycle["player_bedrooms"] == {
        "men": "boys_bedroom",
        "women": "girls_bedroom",
    }

    # 3. The world must not offer a private seventh-resident room, and every
    #    bedroom the player can be assigned to must actually exist.
    world_cfg = cfg["world"]
    loaded = WorldLoader.load_from_file(
        str(Path(STORIES_DIR) / world_cfg["file"]), story_id="six_strangers"
    )
    locations = set(loaded.world_graph.locations)
    assert "player_bedroom" not in locations
    assert set(lifecycle["player_bedrooms"].values()) <= locations

    # 4. Six authored NPCs fill the six slots before the player joins; taking a
    #    slot displaces one same-gender NPC to the entry queue, so the house
    #    holds exactly six residents (player + 5 NPCs) at runtime rather than
    #    seven. Verified through the lifecycle, not by counting authored rows.
    for gender, group in lifecycle["player_slot_groups"].items():
        built = CastLifecycleState.from_config(lifecycle)
        built.choose_initial_roster(group)
        assert len(built.active_ids(group)) == capacities[group] - 1
        other_group = "women" if group == "men" else "men"
        assert len(built.active_ids(other_group)) == capacities[other_group]
        built.reserve_player_slot(group)
        active = built.active_ids()
        assert len(active) == 5, f"{gender}: player + {len(active)} NPCs != 6 residents"
        assert len(built.active_ids(group)) == capacities[group] - 1
        # The displaced housemate is queued for re-entry, not deleted.
        assert built.members[
            next(k for k in built.members if k not in active)
        ].status is CastStatus.UPCOMING
