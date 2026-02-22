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
    assert "RELATIONAL TENSIONS IN THIS SCENE" in sysmsg
    assert "Trust is" in sysmsg
    assert "detective" in sysmsg.lower()


def test_prompt_uses_storyteller_mode_language():
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"

    sysmsg = pb.system_prompt(st, current_user_msg="hello")
    assert "narrative scene engine" in sysmsg.lower()
    assert "story prose" in sysmsg.lower()
    assert "SCENE BRIEF" in sysmsg


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
    assert "IU does not yet know" in sysmsg


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
    assert "Everyone knows this" in sysmsg
    assert "IU does not yet know" in sysmsg
    assert "Bob may have some awareness" in sysmsg


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
    """No transient buffer content should leak into prompt text."""
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
    assert "Player said: hello there" not in sysmsg


def test_prompt_filters_character_extras_by_active_set():
    """Transient extras remain internal and must never be printed in prompt."""
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
    assert "greed" not in sysmsg
    assert "pg13" not in sysmsg


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


# ---------------------------------------------------------------------------
# Prose visibility helpers
# ---------------------------------------------------------------------------

def test_visibility_prose_all_characters():
    from backend.app.engine.prompt_builder import _visibility_prose
    from backend.app.engine.knowledge_chunks import KnowledgeChunk

    chunk = KnowledgeChunk(
        id="t1", text="x", tier="t", source="s", certainty="c",
        known_by=["all_characters"],
    )
    assert _visibility_prose(chunk, {}) == "Everyone knows this."


def test_visibility_prose_single_knower():
    from backend.app.engine.prompt_builder import _visibility_prose
    from backend.app.engine.knowledge_chunks import KnowledgeChunk

    chunk = KnowledgeChunk(
        id="t1", text="x", tier="t", source="s", certainty="c",
        known_by=["iu"],
    )
    chars = {"iu": CharacterState(key="iu", name="IU")}
    assert _visibility_prose(chunk, chars) == "Currently only IU knows this."


def test_visibility_prose_known_and_not_known():
    from backend.app.engine.prompt_builder import _visibility_prose
    from backend.app.engine.knowledge_chunks import KnowledgeChunk

    chunk = KnowledgeChunk(
        id="t1", text="x", tier="t", source="s", certainty="c",
        known_by=["iu"],
        not_known_by=["player"],
        maybe_known_by=["han_jae_seo", "park_so_jin"],
    )
    chars = {
        "iu": CharacterState(key="iu", name="IU"),
        "han_jae_seo": CharacterState(key="han_jae_seo", name="Han Jae-seo"),
        "park_so_jin": CharacterState(key="park_so_jin", name="Park So-jin"),
    }
    result = _visibility_prose(chunk, chars)
    assert "IU knows this" in result
    assert "the player does not yet know" in result
    assert "Han Jae-seo and Park So-jin may have some awareness" in result


def test_visibility_prose_empty_lists():
    from backend.app.engine.prompt_builder import _visibility_prose
    from backend.app.engine.knowledge_chunks import KnowledgeChunk

    chunk = KnowledgeChunk(
        id="t1", text="x", tier="t", source="s", certainty="c",
    )
    assert _visibility_prose(chunk, {}) == ""


def test_knowledge_stack_uses_numbered_list():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.epistemic_state import EpistemicFact

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.add_canonical_fact(EpistemicFact(id="f1", content="Fact one", known_by=["iu"]))
    st.add_canonical_fact(EpistemicFact(id="f2", content="Fact two", known_by=["all_characters"]))

    sysmsg = pb.system_prompt(st)
    # Should have numbered items, not bracketed bullets
    assert "1. " in sysmsg
    assert "- [certain]" not in sysmsg


def test_debug_chunks_structure_unchanged():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.epistemic_state import EpistemicFact

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = CharacterState(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.add_canonical_fact(EpistemicFact(
        id="f1", content="Test fact",
        known_by=["iu"], not_known_by=["player"], maybe_known_by=["bob"],
    ))

    _, layers = pb.system_prompt(st, return_layers=True)
    debug = layers["knowledge_chunks"]
    # Find the fact chunk (skip the character chunk)
    fact_chunk = next(c for c in debug if c["id"] == "fact::f1")
    assert fact_chunk["known_by"] == ["iu"]
    assert fact_chunk["not_known_by"] == ["player"]
    assert fact_chunk["maybe_known_by"] == ["bob"]
    assert fact_chunk["certainty"] == "certain"
