import json

from backend.app.engine.state import (
    init_state,
    apply_state_tag,
    extract_state_tag,
    Character,
)


def test_init_state_defaults():
    st = init_state()
    assert st.minute >= 0
    assert st.turns == 0
    assert st.over is False


def test_apply_state_tag_clamps_relationship_and_updates_main_character():
    st = init_state()
    st.characters["IU"] = Character(key="IU", name="IU", role="ghost")
    st.main_character_id = "IU"

    apply_state_tag(st, {"emotion": "soft", "rel_delta": 1})
    assert st.emotion == "soft"
    assert st.relationship == 1
    assert st.main_character.emotion == "soft"
    assert st.main_character.relationship == 1

    # clamp rel_delta to [-1, 1]
    apply_state_tag(st, {"emotion": "wary", "rel_delta": 999})
    assert st.relationship == 2


def test_extract_state_tag_round_trip_and_strip():
    tag = {"emotion": "wary", "rel_delta": 0}
    reply = "hello\n[[STATE]]" + json.dumps(tag) + "[[/STATE]]\n"
    clean, parsed = extract_state_tag(reply)
    assert "[[STATE]]" not in clean
    assert parsed == tag


def test_extract_state_tag_returns_none_on_invalid_json():
    reply = "oops [[STATE]]{not json}[[/STATE]]"
    clean, parsed = extract_state_tag(reply)
    assert parsed is None
    assert clean == reply


def test_state_has_character_graph_field():
    st = init_state()
    assert st.character_graph is None


def test_apply_state_tag_updates_character_graph():
    from backend.app.engine.character_graph import CharacterGraph

    st = init_state()
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.character_graph = CharacterGraph.from_dict({
        "edges": [{"id": "e1", "from": "iu", "to": "player", "type": "OTHER"}],
    })

    apply_state_tag(st, {"emotion": "warm", "rel_delta": 1})

    edge = st.character_graph.get_edge("iu", "player")
    assert edge is not None
    assert abs(edge.state.affection - 0.1) < 0.001


# ─── BUG-01: add_transient_entry respects expires_after_turns ──────────────

def test_add_transient_entry_respects_custom_ttl():
    """BUG-01: expires_after_turns must be used, not silently ignored."""
    from backend.app.engine.state import GameState
    st = GameState()
    st.add_transient_entry(id="t1", namespace="ns", scope="scene", text="hello", expires_after_turns=1)
    assert len(st.transient_entries) == 1
    assert st.transient_entries[0].turns_remaining == 1


def test_add_transient_entry_uses_default_ttl_when_none():
    """BUG-01: When expires_after_turns is None, the system default is used."""
    from backend.app.config.settings import TRANSIENT_KNOWLEDGE_TURNS
    from backend.app.engine.state import GameState
    st = GameState()
    st.add_transient_entry(id="t2", namespace="ns", scope="scene", text="world", expires_after_turns=None)
    assert st.transient_entries[0].turns_remaining == TRANSIENT_KNOWLEDGE_TURNS


def test_add_transient_entry_ignores_empty_text():
    from backend.app.engine.state import GameState
    st = GameState()
    st.add_transient_entry(id="t3", namespace="ns", scope="scene", text="   ", expires_after_turns=3)
    assert len(st.transient_entries) == 0


# ─── BUG-02: clear_location_transient_entries removes scene entries ─────────

def test_clear_location_transient_entries_removes_scene_entries():
    """BUG-02: Calling clear_location_transient_entries must actually purge entries."""
    from backend.app.engine.state import GameState
    from backend.app.engine.transient_buffer import TransientKnowledge
    st = GameState()
    st.transient_entries = [
        TransientKnowledge(text="Player said something at the apartment", turns_remaining=5),
        TransientKnowledge(text="__active_character_marker__:iu", turns_remaining=5),
        TransientKnowledge(text="knowledge chunk from previous scene", turns_remaining=3),
    ]
    st.clear_location_transient_entries()
    # All non-persistent entries should be gone
    assert len(st.transient_entries) == 0


def test_clear_location_transient_entries_preserves_on_call_markers():
    """BUG-02: On-call phone markers must survive location changes."""
    from backend.app.engine.state import GameState
    from backend.app.engine.transient_buffer import TransientKnowledge
    st = GameState()
    st.transient_entries = [
        TransientKnowledge(text="__on_call_character_marker__:manager", turns_remaining=5),
        TransientKnowledge(text="scene context from previous location", turns_remaining=3),
    ]
    st.clear_location_transient_entries()
    assert len(st.transient_entries) == 1
    assert st.transient_entries[0].text == "__on_call_character_marker__:manager"


# ─── BUG-03: extract_state_tag handles nested JSON objects ──────────────────

def test_extract_state_tag_handles_nested_json():
    """BUG-03: STATE tags with nested JSON objects must parse correctly."""
    tag = {"emotion": "wary", "extra": {"x": 1, "y": 2}}
    reply = "Some text\n[[STATE]]" + json.dumps(tag) + "[[/STATE]]\n"
    clean, parsed = extract_state_tag(reply)
    assert parsed == tag
    assert "[[STATE]]" not in clean


def test_scene_knowledge_fifo_refresh_and_tail_order():
    st = init_state()

    st.upsert_scene_knowledge(
        key="turn:1",
        location_id="room_a",
        speakers=["iu"],
        people_present=["iu", "player"],
        payload={"source": "test"},
    )
    st.upsert_scene_knowledge(
        key="turn:2",
        location_id="room_a",
        speakers=["iu", "player"],
        people_present=["iu", "player"],
        payload={"source": "test"},
    )

    st.upsert_scene_knowledge(
        key="turn:1",
        location_id="room_b",
        speakers=["iu"],
        people_present=["iu"],
        payload={"source": "refresh"},
    )

    keys = [e.key for e in st.scene_knowledge_entries]
    assert keys == ["turn:2", "turn:1"]
    assert st.latest_scene_knowledge() is not None
    assert st.latest_scene_knowledge().location_id == "room_b"


def test_scene_knowledge_fifo_max_len_uses_transient_turn_constant():
    from backend.app.config.settings import TRANSIENT_KNOWLEDGE_TURNS

    st = init_state()
    for idx in range(TRANSIENT_KNOWLEDGE_TURNS + 3):
        st.upsert_scene_knowledge(
            key=f"turn:{idx}",
            location_id=f"loc_{idx}",
            speakers=["iu"],
            people_present=["iu"],
            payload={},
        )

    assert len(st.scene_knowledge_entries) == TRANSIENT_KNOWLEDGE_TURNS
    assert st.scene_knowledge_entries[0].key == "turn:3"

from backend.app.engine.state import init_state
from backend.app.engine.transient_buffer import TransientKnowledge, prune_expired
from backend.app.config.settings import TRANSIENT_KNOWLEDGE_TURNS


def test_prune_expired_by_turns():
    e1 = TransientKnowledge(text="hello", turns_remaining=1)
    e2 = TransientKnowledge(text="fresh", turns_remaining=2)

    kept = prune_expired([e1, e2], current_turn=4, current_minute=0)
    texts = [e.text for e in kept]
    assert "hello" not in texts
    assert "fresh" in texts
    assert kept[0].turns_remaining == 1


def test_state_purge_transient_entries():
    st = init_state()
    st.story = "demo"
    st.turns = 0
    st.minute = 0

    # BUG-01 fix: expires_after_turns=1 must result in TTL=1, not TRANSIENT_KNOWLEDGE_TURNS.
    st.add_transient_entry(
        id="t1",
        namespace="default_user-demo-1",
        scope="conversation",
        text="Player said hi",
        expires_after_turns=1,
    )
    assert len(st.transient_entries) == 1
    assert st.transient_entries[0].turns_remaining == 1  # BUG-01 fixed: respects caller TTL

    # A single purge call should expire the 1-turn entry.
    st.turns = 1
    st.purge_transient_entries()

    assert len(st.transient_entries) == 0


def test_transient_entries_use_default_ttl_of_eight():
    st = init_state()
    st.story = "demo"

    st.add_transient_entry(
        id="t1",
        namespace="default_user-demo-1",
        scope="conversation",
        text="One",
    )
    assert len(st.transient_entries) == 1
    assert st.transient_entries[0].turns_remaining == TRANSIENT_KNOWLEDGE_TURNS


# ─── BL-07: per-character self_knowledge round-trips through Character ──────

def test_character_from_dict_parses_self_knowledge_when_present():
    ch = Character.from_dict({
        "key": "daeho",
        "name": "Dae-ho",
        "self_knowledge": ["You are quietly proud.", "You hate asking for help."],
    })
    assert ch.self_knowledge == ["You are quietly proud.", "You hate asking for help."]
    # Must not leak into the meta forward-compat bucket.
    assert "self_knowledge" not in ch.meta


def test_character_from_dict_self_knowledge_absent_defaults_to_empty_list():
    ch = Character.from_dict({"key": "npc", "name": "NPC"})
    assert ch.self_knowledge == []


def test_character_from_dict_self_knowledge_drops_blank_entries():
    ch = Character.from_dict({
        "key": "npc",
        "name": "NPC",
        "self_knowledge": ["Real entry.", "   ", "", "Another real one."],
    })
    assert ch.self_knowledge == ["Real entry.", "Another real one."]


def test_character_to_dict_serializes_self_knowledge():
    ch = Character(key="mina", name="Mina", self_knowledge=["You love mornings."])
    d = ch.to_dict()
    assert d["self_knowledge"] == ["You love mornings."]


def test_character_self_knowledge_round_trips_from_dict_to_dict():
    original = {
        "key": "priya",
        "name": "Priya",
        "role": "housemate",
        "self_knowledge": ["You are fiercely independent."],
    }
    ch = Character.from_dict(original)
    round_tripped = Character.from_dict(ch.to_dict())
    assert round_tripped.self_knowledge == ["You are fiercely independent."]


# ─── Character.voice: authored speech-style cues, distinct from self_knowledge ──

def test_character_from_dict_parses_voice_when_present():
    ch = Character.from_dict({
        "key": "daeho",
        "name": "Dae-ho",
        "voice": ["Short, clipped sentences.", "Never uses contractions."],
    })
    assert ch.voice == ["Short, clipped sentences.", "Never uses contractions."]
    assert "voice" not in ch.meta


def test_character_from_dict_voice_absent_defaults_to_empty_list():
    ch = Character.from_dict({"key": "npc", "name": "NPC"})
    assert ch.voice == []


def test_character_from_dict_voice_drops_blank_entries():
    ch = Character.from_dict({
        "key": "npc",
        "name": "NPC",
        "voice": ["Real cue.", "   ", "", "Another real cue."],
    })
    assert ch.voice == ["Real cue.", "Another real cue."]


def test_character_to_dict_serializes_voice():
    ch = Character(key="mina", name="Mina", voice=["Talks in run-on sentences."])
    d = ch.to_dict()
    assert d["voice"] == ["Talks in run-on sentences."]


def test_character_voice_round_trips_from_dict_to_dict():
    original = {
        "key": "priya",
        "name": "Priya",
        "role": "housemate",
        "voice": ["Answers questions with a question."],
    }
    ch = Character.from_dict(original)
    round_tripped = Character.from_dict(ch.to_dict())
    assert round_tripped.voice == ["Answers questions with a question."]


# ============================================================================
# Phase 3 "Social life": Character.goal seeded from authored motive/goal,
# and Character.tells preserved. This is the regression test proving the
# real drop-bug is fixed - `motive`/`tells` previously fell silently into
# the unused `meta` bucket with zero readers anywhere in the codebase.
# ============================================================================

def test_character_from_dict_seeds_goal_from_motive():
    ch = Character.from_dict({
        "key": "makoto", "name": "Makoto",
        "motive": "Make real friends and find room for romance.",
    })
    assert ch.goal is not None
    assert ch.goal.current == "Make real friends and find room for romance."
    assert ch.goal.subject_id == "makoto"
    assert len(ch.goal.history) == 1
    assert ch.goal.history[0].source == "author"
    # Must not leak into the meta forward-compat bucket.
    assert "motive" not in ch.meta


def test_character_from_dict_seeds_goal_from_generic_goal_string():
    ch = Character.from_dict({"key": "npc", "name": "NPC", "goal": "Escape the house unnoticed."})
    assert ch.goal is not None
    assert ch.goal.current == "Escape the house unnoticed."


def test_character_from_dict_motive_takes_priority_over_goal_string():
    ch = Character.from_dict({"key": "npc", "name": "NPC", "motive": "M", "goal": "G"})
    assert ch.goal.current == "M"


def test_character_from_dict_no_motive_or_goal_leaves_goal_none():
    ch = Character.from_dict({"key": "npc", "name": "NPC"})
    assert ch.goal is None


def test_character_from_dict_ignores_non_character_goal_dict():
    """A raw {'goal': {'win_text_rule': ...}} shape (the murder-mystery
    session-level win-condition object, not a serialized EvolvingTrait and
    not a character motive) must not be mistaken for a character goal."""
    ch = Character.from_dict({"key": "npc", "name": "NPC", "goal": {"win_text_rule": "..."}})
    assert ch.goal is None


def test_character_from_dict_restores_serialized_goal_trait():
    """A full serialized EvolvingTrait dict (the shape produced by
    Character.to_dict(), e.g. session restore) must restore the whole
    object including history, not just seed a fresh single-entry trait."""
    ch = Character.from_dict({
        "key": "makoto", "name": "Makoto",
        "goal": {
            "kind": "goal", "subject_id": "makoto", "target_id": "", "current": "new goal",
            "confidence": 0.8,
            "history": [
                {"id": "goal:makoto::0", "content": "old goal", "source": "author", "confidence": 1.0, "timestamp_minute": 0, "provenance": "author"},
                {"id": "shift_1", "content": "new goal", "source": "extractor", "confidence": 0.8, "timestamp_minute": 500, "provenance": "changed behavior"},
            ],
        },
    })
    assert ch.goal.current == "new goal"
    assert len(ch.goal.history) == 2
    assert ch.goal.history[0].content == "old goal"


def test_character_from_dict_seeds_tells():
    ch = Character.from_dict({
        "key": "yoo_min_ho", "name": "Yoo Min-ho", "is_suspect": True,
        "tells": ["voice tremor on logistics questions", "avoids eye contact"],
    })
    assert ch.tells == ["voice tremor on logistics questions", "avoids eye contact"]
    assert "tells" not in ch.meta


def test_character_to_dict_serializes_goal_and_tells():
    ch = Character.from_dict({
        "key": "iu", "name": "IU", "motive": "Find the truth.", "tells": ["fidgets when lying"],
    })
    d = ch.to_dict()
    assert d["goal"]["current"] == "Find the truth."
    assert d["tells"] == ["fidgets when lying"]


def test_character_goal_round_trips_from_dict_to_dict_with_full_history():
    ch = Character.from_dict({"key": "makoto", "name": "Makoto", "motive": "Original motive."})
    ch.goal.propose_change(
        "Changed motive.", minute=500, reason="behavior shift", confidence=0.7, entry_id="shift_1",
    )
    round_tripped = Character.from_dict(ch.to_dict())
    assert round_tripped.goal.current == "Changed motive."
    assert len(round_tripped.goal.history) == 2
    assert round_tripped.goal.history[0].content == "Original motive."
