# tests/backend/app/engine/test_active_characters.py
"""Tests for context-aware character mention detection."""

from backend.app.engine.active_characters import (
    compute_active_character_set,
    detect_mentioned_characters,
    get_character_location_index,
    get_on_call_character_keys,
    get_location_speaker_keys,
)
from backend.app.engine.state import CharacterState, GameState


def _make_characters():
    return {
        "iu": CharacterState(key="iu", name="IU", role="ghost"),
        "yoo_min_ho": CharacterState(key="yoo_min_ho", name="Yoo Min-ho", role="manager"),
        "han_jae_seo": CharacterState(key="han_jae_seo", name="Han Jae-seo", role="ceo"),
        "park_so_jin": CharacterState(key="park_so_jin", name="Park So-jin", role="friend"),
        "rival_trainee": CharacterState(key="rival_trainee", name="Unnamed Rival Trainee", role="other"),
    }


# ---------------------------------------------------------------------------
# detect_mentioned_characters
# ---------------------------------------------------------------------------

def test_detect_by_full_name():
    chars = _make_characters()
    result = detect_mentioned_characters("Tell me about Yoo Min-ho", chars, "iu")
    assert "yoo_min_ho" in result
    assert "iu" in result      # always-active
    assert "player" in result  # always-active


def test_detect_by_partial_name_token():
    chars = _make_characters()
    # "Min" is 3 chars, should match Yoo Min-ho
    result = detect_mentioned_characters("What did Min-ho say?", chars, "iu")
    assert "yoo_min_ho" in result


def test_detect_by_key_with_underscores():
    chars = _make_characters()
    result = detect_mentioned_characters("Ask park_so_jin about it", chars, "iu")
    assert "park_so_jin" in result


def test_detect_by_key_with_spaces():
    chars = _make_characters()
    result = detect_mentioned_characters("Ask park so jin about it", chars, "iu")
    assert "park_so_jin" in result


def test_no_match_returns_defaults_only():
    chars = _make_characters()
    result = detect_mentioned_characters("Hello there", chars, "iu")
    assert result == {"iu", "player"}


def test_short_name_exact_match():
    """IU is only 2 chars — must match via exact name, not token matching."""
    chars = _make_characters()
    result = detect_mentioned_characters("What does IU think about that?", chars, "iu")
    assert "iu" in result


def test_short_token_no_false_positive():
    """Tokens under 3 chars should not cause false positives."""
    chars = {
        "li_na": CharacterState(key="li_na", name="Li Na", role="npc"),
    }
    # "li" is 2 chars, should NOT match "earlier" via token matching
    result = detect_mentioned_characters("I came here earlier today", chars, "main")
    assert "li_na" not in result


def test_empty_text_returns_defaults():
    chars = _make_characters()
    result = detect_mentioned_characters("", chars, "iu")
    assert result == {"iu", "player"}


def test_case_insensitive_matching():
    chars = _make_characters()
    result = detect_mentioned_characters("what about HAN JAE-SEO?", chars, "iu")
    assert "han_jae_seo" in result


def test_multiple_characters_detected():
    chars = _make_characters()
    result = detect_mentioned_characters(
        "Did Han Jae-seo and Park So-jin meet that night?", chars, "iu"
    )
    assert "han_jae_seo" in result
    assert "park_so_jin" in result


# ---------------------------------------------------------------------------
# get_location_speaker_keys
# ---------------------------------------------------------------------------

def test_location_speakers_maps_name_to_key():
    state = GameState()
    state.location_id = "room_a"
    state.characters = {
        "steve": CharacterState(key="steve", name="Steve", role="suspect"),
    }
    state.story_cfg = {
        "world": {"location_speakers": {"room_a": "Steve"}},
    }
    result = get_location_speaker_keys(state)
    assert result == {"steve"}


def test_location_speakers_list_format():
    state = GameState()
    state.location_id = "room_b"
    state.characters = {
        "alice": CharacterState(key="alice", name="Alice", role="npc"),
        "bob": CharacterState(key="bob", name="Bob", role="npc"),
    }
    state.story_cfg = {
        "world": {"location_speakers": {"room_b": ["Alice", "Bob"]}},
    }
    result = get_location_speaker_keys(state)
    assert result == {"alice", "bob"}


def test_location_speakers_no_mapping():
    state = GameState()
    state.location_id = "room_c"
    state.story_cfg = {"world": {}}
    result = get_location_speaker_keys(state)
    assert result == set()


def test_location_speakers_no_story_cfg():
    state = GameState()
    result = get_location_speaker_keys(state)
    assert result == set()


def test_character_location_index_maps_all_bindings():
    state = GameState()
    state.characters = {
        "iu": CharacterState(key="iu", name="IU", role="ghost"),
        "han_jae_seo": CharacterState(key="han_jae_seo", name="Han Jae-seo", role="ceo"),
    }
    state.story_cfg = {
        "world": {
            "location_speakers": {
                "iu_apartment": ["IU"],
                "aster_office": ["Han Jae-seo"],
            }
        }
    }

    result = get_character_location_index(state)
    assert result["iu"] == "iu_apartment"
    assert result["han_jae_seo"] == "aster_office"


# ---------------------------------------------------------------------------
# compute_active_character_set
# ---------------------------------------------------------------------------

def test_compute_combines_all_sources():
    state = GameState()
    state.main_character_id = "iu"
    state.characters = _make_characters()
    state.location_id = "lobby"
    state.story_cfg = {
        "world": {"location_speakers": {"lobby": "Park So-jin"}},
    }

    result = compute_active_character_set(
        state=state,
        user_msg="Tell me about Han Jae-seo",
        recent_log=[],
    )

    assert "iu" in result          # always-active (main)
    assert "player" in result      # always-active
    assert "han_jae_seo" in result # mentioned in user_msg
    assert "park_so_jin" in result # location speaker


def test_compute_ignores_recent_log_to_avoid_stale_mentions():
    state = GameState()
    state.main_character_id = "iu"
    state.characters = _make_characters()

    result = compute_active_character_set(
        state=state,
        user_msg="hello",
        recent_log=[
            {"role": "assistant", "content": "Min-ho visited yesterday"},
        ],
    )

    assert "yoo_min_ho" not in result


def test_compute_ignores_system_role_recent_log_entries():
    state = GameState()
    state.main_character_id = "iu"
    state.characters = _make_characters()

    result = compute_active_character_set(
        state=state,
        user_msg="hello",
        recent_log=[
            {"role": "system", "content": "Han Jae-seo Park So-jin Yoo Min-ho Rival Trainee"},
        ],
    )

    assert result == {"iu", "player"}


def test_compute_includes_npc_reply():
    state = GameState()
    state.main_character_id = "iu"
    state.characters = _make_characters()

    result = compute_active_character_set(
        state=state,
        user_msg="",
        recent_log=[],
        npc_reply="I spoke with Park So-jin last night.",
    )

    assert "park_so_jin" in result


def test_get_on_call_character_keys_reads_transient_markers():
    state = GameState()
    state.add_transient_entry(
        id="on_call::yoo_min_ho",
        namespace="test",
        scope="scene",
        text="__on_call_character_marker__:yoo_min_ho",
        expires_after_turns=4,
    )
    result = get_on_call_character_keys(state)
    assert result == {"yoo_min_ho"}


def test_compute_includes_on_call_markers():
    state = GameState()
    state.main_character_id = "iu"
    state.characters = _make_characters()
    state.add_transient_entry(
        id="on_call::han_jae_seo",
        namespace="test",
        scope="scene",
        text="__on_call_character_marker__:han_jae_seo",
        expires_after_turns=4,
    )

    result = compute_active_character_set(
        state=state,
        user_msg="hello",
        recent_log=[],
    )

    assert "han_jae_seo" in result


def test_compute_excludes_offscene_location_speakers_by_current_location():
    state = GameState()
    state.main_character_id = "iu"
    state.characters = _make_characters()
    state.location_id = "iu_apartment"
    state.story_cfg = {
        "world": {
            "location_speakers": {
                "iu_apartment": ["IU"],
                "aster_office": ["Han Jae-seo"],
            }
        }
    }

    result = compute_active_character_set(
        state=state,
        user_msg="hello",
        recent_log=[],
    )

    assert "iu" in result
    assert "han_jae_seo" not in result
