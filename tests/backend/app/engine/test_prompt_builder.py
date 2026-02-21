import re

import pytest

from backend.app.engine.state import init_state, CharacterState


def test_system_prompt_includes_required_tail_and_memory_block(monkeypatch):
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {
        "meta": {"disclaimer": "fiction"},
    }
    st.characters["IU"] = CharacterState(key="IU", name="IU", role="ghost")
    st.main_character_id = "IU"

    memory = pb._format_memory_block([
        {"type": "discography", "chunk_id": "song_love_poem", "text": "IU - Love Poem"}
    ])
    sysmsg = pb.system_prompt(st, is_first_turn=True, memory_block=memory)

    assert "EPISTEMIC KNOWLEDGE STACK" in sysmsg
    assert "[[STATE]]" in sysmsg and "[[/STATE]]" in sysmsg


def test_build_messages_trims_history_and_adds_header(monkeypatch):
    from backend.app.engine import prompt_builder as pb

    # Avoid runtime knowledge retrieval in tests.
    monkeypatch.setattr(pb, "retrieve_knowledge", lambda *a, **k: ([], {}), raising=False)

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["IU"] = CharacterState(key="IU", name="IU", role="ghost")
    st.main_character_id = "IU"

    # Create a long log and ensure prompt_builder trims it.
    log = []
    for i in range(50):
        log.append({"role": "user", "content": f"u{i}"})
        log.append({"role": "assistant", "content": f"a{i}"})

    messages = pb.build_messages(st, log, "hello there", [])
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert "Time:" in messages[-1]["content"]

    # Ensure the state tag requirement exists in system prompt.
    assert "REQUIRED FINAL LINE" in messages[0]["content"]
    # Make sure casual Korean detection doesn't crash
    assert isinstance(st.casual_korean_used, list)


def test_format_memory_block_empty_is_blank():
    from backend.app.engine import prompt_builder as pb
    assert pb._format_memory_block([]) == ""


def test_prompt_includes_relationship_section():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.character_graph import CharacterGraph

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}, "setting": {}, "victim": {}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.character_graph = CharacterGraph.from_dict({
        "edges": [{
            "id": "e1", "from": "iu", "to": "player", "type": "OTHER",
            "state": {"trust": -0.3, "fear": 0.7},
            "label": "The detective interrogating you.",
        }],
    })

    sysmsg = pb.system_prompt(st)
    assert "YOUR FEELINGS ABOUT THE PEOPLE YOU KNOW" in sysmsg
    assert "Trust:" in sysmsg
    assert "detective" in sysmsg.lower()


def test_prompt_ignores_story_specific_fields_and_uses_canonical_facts():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.epistemic_state import EpistemicFact

    st = init_state()
    st.story_cfg = {
        "meta": {"disclaimer": "fiction"},
        "world_context": ["this should not appear"],
        "prompt_suggestions": ["this should not appear"],
        "characters": [{"key": "iu", "name": "IU", "motive": "hidden motive"}],
    }
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.add_canonical_fact(EpistemicFact(id="f1", content="Canonical fact for IU", known_by=["iu"]))

    sysmsg = pb.system_prompt(st)
    assert "EPISTEMIC KNOWLEDGE STACK" in sysmsg
    assert "Canonical fact for IU" in sysmsg
    assert "this should not appear" not in sysmsg
    assert "hidden motive" not in sysmsg


def test_prompt_layers_dict_has_new_keys():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.character_graph import CharacterGraph

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}, "setting": {}, "victim": {}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.character_graph = CharacterGraph.from_dict({
        "edges": [{"id": "e1", "from": "iu", "to": "player", "type": "OTHER"}],
    })

    sysmsg, layers = pb.system_prompt(st, return_layers=True)
    assert "relationship_context" in layers
    assert "knowledge_stack" in layers
    assert "knowledge_chunks" in layers
    assert "transient_buffer" in layers


def test_prompt_labels_canonical_truths_with_known_by_visibility():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.epistemic_state import EpistemicFact

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"

    st.add_canonical_fact(EpistemicFact(id="visible", content="IU known fact", known_by=["iu"]))
    st.add_canonical_fact(EpistemicFact(id="hidden", content="Player-only fact", known_by=["player"], not_known_by=["iu"]))

    sysmsg = pb.system_prompt(st)
    assert "IU known fact" in sysmsg
    assert "Player-only fact" in sysmsg
    assert "not_known_by=iu" in sysmsg


def test_prompt_knowledge_stack_renders_visibility_labels():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.epistemic_state import EpistemicFact

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"

    st.add_canonical_fact(EpistemicFact(
        id="common",
        content="Common fact visible to all.",
        known_by=["all_characters"],
    ))
    st.add_canonical_fact(EpistemicFact(
        id="hidden",
        content="Hidden fact not known by IU.",
        known_by=["player"],
        not_known_by=["iu"],
        maybe_known_by=["bob"],
    ))

    sysmsg = pb.system_prompt(st)
    assert "EPISTEMIC KNOWLEDGE STACK" in sysmsg
    assert "known_by=ALL_CHARACTERS" in sysmsg
    assert "not_known_by=iu" in sysmsg
    assert "maybe_known_by=bob" in sysmsg


# ---------------------------------------------------------------------------
# Active-character graph filtering
# ---------------------------------------------------------------------------

def test_prompt_filters_graph_edges_by_active_characters():
    """Graph edges for non-active characters should not appear in prompt."""
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.character_graph import CharacterGraph

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.characters["bob"] = CharacterState(key="bob", name="Bob", role="suspect")
    st.main_character_id = "iu"
    st.character_graph = CharacterGraph.from_dict({
        "edges": [
            {"id": "e1", "from": "iu", "to": "player", "type": "OTHER",
             "label": "The detective."},
            {"id": "e2", "from": "iu", "to": "bob", "type": "FRIEND",
             "label": "Old buddy."},
        ],
    })

    # Add active marker for player only (not bob)
    st.add_transient_entry(
        id="active_char::player",
        namespace="test",
        scope="scene",
        text="__active_character_marker__:player",
        expires_after_turns=4,
        meta={"source": "active_character", "character_key": "player"},
    )

    sysmsg = pb.system_prompt(st)
    # Player relationship should be present
    assert "detective" in sysmsg.lower()
    # Bob should NOT appear in the relationships section
    assert "old buddy" not in sysmsg.lower()


def test_prompt_hides_active_character_markers_from_text():
    """Active character markers must not leak into prompt text."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"

    st.add_transient_entry(
        id="active_char::player",
        namespace="test",
        scope="scene",
        text="__active_character_marker__:player",
        expires_after_turns=4,
        meta={"source": "active_character", "character_key": "player"},
    )
    st.add_transient_entry(
        id="conv_1",
        namespace="test",
        scope="conversation",
        text="Player said: hello there",
        expires_after_turns=2,
        meta={"source": "player"},
    )

    sysmsg = pb.system_prompt(st)
    assert "__active_character_marker__" not in sysmsg
    assert "Player said: hello there" in sysmsg


def test_prompt_filters_character_extras_by_active_set():
    """Character extras for non-active characters should be filtered out."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.characters["bob"] = CharacterState(key="bob", name="Bob", role="suspect")
    st.main_character_id = "iu"

    # Bob extras (should be filtered since bob is not active)
    st.add_transient_entry(
        id="story_extra_bob",
        namespace="test",
        scope="scene",
        text='character.bob.extras: {"motive": "greed"}',
        expires_after_turns=12,
        meta={"source": "story_noncanonical", "character_key": "bob"},
    )
    # Story-level entry (no character_key, should always appear)
    st.add_transient_entry(
        id="story_extra_rules",
        namespace="test",
        scope="scene",
        text='story.rules: {"pg13": true}',
        expires_after_turns=12,
        meta={"source": "story_noncanonical"},
    )

    # Only player is active
    st.add_transient_entry(
        id="active_char::player",
        namespace="test",
        scope="scene",
        text="__active_character_marker__:player",
        expires_after_turns=4,
        meta={"source": "active_character", "character_key": "player"},
    )

    sysmsg = pb.system_prompt(st)
    assert "greed" not in sysmsg        # bob's extras filtered
    assert "pg13" in sysmsg             # story-level entry preserved


def test_prompt_backward_compat_no_markers():
    """With no active-character markers, only main+player edges appear."""
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.character_graph import CharacterGraph

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.characters["bob"] = CharacterState(key="bob", name="Bob", role="suspect")
    st.main_character_id = "iu"
    st.character_graph = CharacterGraph.from_dict({
        "edges": [
            {"id": "e1", "from": "iu", "to": "player", "type": "OTHER",
             "label": "The detective."},
            {"id": "e2", "from": "iu", "to": "bob", "type": "FRIEND",
             "label": "Old buddy."},
        ],
    })

    # No active_character markers at all — fallback is {main, player}
    sysmsg = pb.system_prompt(st)
    assert "detective" in sysmsg.lower()
    # Bob is NOT in the default fallback set {iu, player}
    assert "old buddy" not in sysmsg.lower()
