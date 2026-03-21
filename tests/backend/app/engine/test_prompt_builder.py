

from backend.app.engine.state import init_state, Character


def test_system_prompt_includes_epistemic_stack(monkeypatch):
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {
        "meta": {"disclaimer": "fiction"},
    }
    st.characters["IU"] = Character(key="IU", name="IU", role="ghost")
    st.main_character_id = "IU"

    memory = pb._format_memory_block([
        {"type": "discography", "chunk_id": "song_love_poem", "text": "IU - Love Poem"}
    ])
    sysmsg = pb.system_prompt(st, is_first_turn=True, memory_block=memory)

    assert "EPISTEMIC KNOWLEDGE STACK" in sysmsg
    assert "REQUIRED FINAL LINE" not in sysmsg


def test_build_messages_trims_history_and_adds_header(monkeypatch):
    from backend.app.engine import prompt_builder as pb

    # Avoid runtime knowledge retrieval in tests.
    monkeypatch.setattr(pb, "retrieve_knowledge", lambda *a, **k: ([], {}), raising=False)

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["IU"] = Character(key="IU", name="IU", role="ghost")
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

    # State tag is optional; prompt should not force a terminal line.
    assert "REQUIRED FINAL LINE" not in messages[0]["content"]
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
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.character_graph = CharacterGraph.from_dict({
        "edges": [{
            "id": "e1", "from": "iu", "to": "player", "type": "OTHER",
            "state": {"trust": -0.3, "fear": 0.7},
            "label": "The detective interrogating you.",
        }],
    })

    sysmsg = pb.system_prompt(st)
    assert "RELATIONSHIP CONTEXT IN THIS SCENE" in sysmsg
    assert "IU currently reads the player" in sysmsg
    assert "detective" in sysmsg.lower()


def test_prompt_uses_storyteller_mode_language():
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"

    sysmsg = pb.system_prompt(st, current_user_msg="hello")
    assert "narrative scene engine" in sysmsg.lower()
    assert "story prose" in sysmsg.lower()
    assert "SCENE BRIEF" in sysmsg


def test_scene_brief_includes_people_present_and_speakers():
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.characters["park_so_jin"] = Character(key="park_so_jin", name="Park So-jin", role="producer")
    st.main_character_id = "iu"

    st.add_transient_entry(
        id="pp::iu",
        namespace="test",
        scope="scene",
        text="__people_present_marker__:iu",
        expires_after_turns=4,
    )
    st.add_transient_entry(
        id="pp::park_so_jin",
        namespace="test",
        scope="scene",
        text="__people_present_marker__:park_so_jin",
        expires_after_turns=4,
    )
    st.add_transient_entry(
        id="speaker::iu",
        namespace="test",
        scope="scene",
        text="__scene_speaker_marker__:iu",
        expires_after_turns=4,
    )

    sysmsg = pb.system_prompt(st, current_user_msg="hello")
    assert "People present in this location right now (2):" in sysmsg
    assert "Current-turn speakers:" in sysmsg


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
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
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
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
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
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
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
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
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
    # common-knowledge facts now appear under the grouped sub-heading rather than
    # with an inline "Everyone knows this." annotation
    assert "Common knowledge" in sysmsg
    assert "IU does not yet know" in sysmsg
    assert "Bob may have some awareness" not in sysmsg


# ---------------------------------------------------------------------------
# Active-character graph filtering
# ---------------------------------------------------------------------------

def test_prompt_filters_graph_edges_by_active_characters():
    """Graph edges for non-active characters should not appear in prompt."""
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.character_graph import CharacterGraph

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.characters["bob"] = Character(key="bob", name="Bob", role="suspect")
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
    assert "the player" in sysmsg.lower()
    # Bob should NOT appear in the relationships section
    assert "old buddy" not in sysmsg.lower()


def test_prompt_hides_active_character_markers_from_text():
    """No transient buffer content should leak into prompt text."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
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
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.characters["bob"] = Character(key="bob", name="Bob", role="suspect")
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
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.characters["bob"] = Character(key="bob", name="Bob", role="suspect")
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
    assert "the player" in sysmsg.lower()
    # Bob is NOT in the default fallback set {iu, player}
    assert "old buddy" not in sysmsg.lower()


def test_prompt_does_not_duplicate_relationship_context_in_knowledge_stack():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.character_graph import CharacterGraph

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.character_graph = CharacterGraph.from_dict({
        "edges": [{"id": "e1", "from": "iu", "to": "player", "type": "OTHER"}],
    })

    sysmsg = pb.system_prompt(st)
    # No raw graph-edge telemetry in epistemic stack.
    assert "iu->player type=" not in sysmsg
    # Relationship section should still exist once.
    assert sysmsg.count("RELATIONSHIP CONTEXT IN THIS SCENE") == 1


def test_prompt_filters_legacy_relationship_telemetry_from_stack():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.character_graph import CharacterGraph
    from backend.app.engine.epistemic_state import EpistemicFact

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.character_graph = CharacterGraph.from_dict({
        "edges": [{"id": "e1", "from": "iu", "to": "player", "type": "OTHER"}],
    })

    st.add_canonical_fact(EpistemicFact(
        id="legacy_rel",
        content="iu->player type=OTHER Trust is neutral; fear is unfazed; affection is neutral; suspicion is fully_trusting.",
        known_by=["iu", "player"],
    ))

    sysmsg = pb.system_prompt(st)
    assert "iu->player type=OTHER" not in sysmsg
    assert "Relationship dynamics and world context:" not in sysmsg
    assert sysmsg.count("RELATIONSHIP CONTEXT IN THIS SCENE") == 1


def test_prompt_hides_offscene_visibility_names_from_epistemic_stack():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.epistemic_state import EpistemicFact

    st = init_state()
    st.story_cfg = {
        "meta": {"disclaimer": "fiction"},
        "world": {"location_speakers": {"iu_apartment": ["IU"]}},
    }
    st.location_id = "iu_apartment"
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.characters["han_jae_seo"] = Character(key="han_jae_seo", name="Han Jae-seo", role="ceo")
    st.main_character_id = "iu"

    st.add_canonical_fact(EpistemicFact(
        id="f1",
        content="A private detail about the death.",
        known_by=["iu"],
        maybe_known_by=["han_jae_seo"],
    ))

    sysmsg = pb.system_prompt(st)
    assert "Han Jae-seo" not in sysmsg


def test_prompt_world_context_uses_natural_place_prose():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.world.location import Location

    class _WG:
        def get_location(self, loc_id):
            return Location(
                id=loc_id,
                name="IU's Apartment",
                description="A quiet apartment filled with muted light.",
            )

    class _RT:
        world_graph = _WG()

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.location_id = "iu_apartment"
    st.world_runtime = _RT()

    sysmsg = pb.system_prompt(st)
    assert "The current place is IU's Apartment." in sysmsg
    assert "Current place=" not in sysmsg


def test_relationship_section_uses_natural_prose_and_role_details():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.character_graph import CharacterGraph

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.characters["han_jae_seo"] = Character(key="han_jae_seo", name="Han Jae-seo", role="ceo")
    st.main_character_id = "iu"
    st.character_graph = CharacterGraph.from_dict({
        "edges": [
            {
                "id": "e1",
                "from": "iu",
                "to": "han_jae_seo",
                "type": "EMPLOYER",
                "state": {
                    "trust": -0.5,
                    "fear": 0.6,
                    "affection": -0.4,
                    "suspicion": 0.75,
                },
            }
        ],
    })
    st.add_transient_entry(
        id="active_char::han_jae_seo",
        namespace="test",
        scope="scene",
        text="__active_character_marker__:han_jae_seo",
        expires_after_turns=4,
    )

    sysmsg = pb.system_prompt(st)
    assert "This is an employer relationship with a clear boss-to-subordinate power dynamic." in sysmsg
    assert "highly suspicious suspicion" in sysmsg
    assert "highly_suspicious" not in sysmsg


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
    chars = {"iu": Character(key="iu", name="IU")}
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
        "iu": Character(key="iu", name="IU"),
        "han_jae_seo": Character(key="han_jae_seo", name="Han Jae-seo"),
        "park_so_jin": Character(key="park_so_jin", name="Park So-jin"),
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
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
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
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
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


def test_certainty_word_mapping_uses_tenths():
    from backend.app.engine.prompt_builder import _certainty_word

    assert _certainty_word(0.0) == "speculative"
    assert _certainty_word(0.14) == "very_tentative"
    assert _certainty_word(0.24) == "tentative"
    assert _certainty_word(0.26) == "leaning_uncertain"
    assert _certainty_word(0.5) == "mixed"
    assert _certainty_word(0.84) == "likely"
    assert _certainty_word(1.0) == "certain"


def test_certainty_phrase_buckets_are_natural():
    from backend.app.engine.prompt_builder import _certainty_phrase

    assert _certainty_phrase("speculative") == "with very low confidence"
    assert _certainty_phrase("uncertain") == "with low confidence"
    assert _certainty_phrase("mixed") == "with mixed confidence"
    assert _certainty_phrase("plausible") == "with moderate confidence"
    assert _certainty_phrase("likely") == "with high confidence"
    assert _certainty_phrase("certain") == "with complete confidence"


def test_belief_section_includes_certainty_words_before_fact_text():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.epistemic_state import EpistemicClaim, BeliefState

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"

    bs = BeliefState(character_id="iu")
    bs.add_claim(EpistemicClaim(
        id="b1",
        content="IU died the prior week in the Nonhyeon-dong officetel closet; she is now the ghost in the apartment.",
        confidence=0.3,
        known_by=["iu"],
    ))
    st.beliefs["iu"] = bs

    sysmsg = pb.system_prompt(st)
    assert "Beliefs and suspicions (not necessarily true):" in sysmsg
    assert "Currently only IU knows this with low confidence: IU died the prior week" in sysmsg


def test_belief_section_snapshot_layout_is_stable():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.epistemic_state import EpistemicClaim, BeliefState

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.characters["player"] = Character(key="player", name="The Player", role="detective")
    st.main_character_id = "iu"

    bs = BeliefState(character_id="iu")
    bs.add_claim(EpistemicClaim(
        id="b_low",
        content="I may have heard footsteps by the closet before dawn.",
        confidence=0.2,
        known_by=["iu"],
    ))
    bs.add_claim(EpistemicClaim(
        id="b_high",
        content="My phone and lyric notebook were missing after the killing.",
        confidence=0.9,
        known_by=["iu"],
        not_known_by=["player"],
    ))
    st.beliefs["iu"] = bs

    sysmsg = pb.system_prompt(st)
    section = sysmsg.split("Beliefs and suspicions (not necessarily true):\n", 1)[1].strip()

    expected = (
        "1. Currently only IU knows this with low confidence: I may have heard footsteps by the closet before dawn.\n"
        "2. IU knows this but the player does not yet know with high confidence: My phone and lyric notebook were missing after the killing."
    )
    assert section == expected


# ─── BUG-12: _relationship_role_prose handles "npc" and generic roles ────────

def test_relationship_role_prose_npc_returns_helpful_message():
    """BUG-12: 'npc' role should not produce the ugly 'The relationship type is npc.' message."""
    from backend.app.engine.prompt_builder import _relationship_role_prose
    result = _relationship_role_prose("npc")
    assert "The relationship type is npc" not in result
    assert len(result) > 0


def test_relationship_role_prose_character_fallback():
    """BUG-12: 'character' and 'other' and empty string are also handled."""
    from backend.app.engine.prompt_builder import _relationship_role_prose
    for role in ("character", "other", ""):
        result = _relationship_role_prose(role)
        assert f"The relationship type is {role}" not in result


def test_relationship_role_prose_known_roles_unchanged():
    """BUG-12: Verify known named roles still return their specific prose."""
    from backend.app.engine.prompt_builder import _relationship_role_prose
    assert "employer" in _relationship_role_prose("employer").lower()
    assert "family" in _relationship_role_prose("family").lower()
    assert "romantic" in _relationship_role_prose("lover").lower()


def test_character_identity_section_injected_when_present():
    """character_self_knowledge entries are directly injected as a named section."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {
        "character_self_knowledge": [
            "You are a ghost.",
            "You died in this apartment.",
        ]
    }
    st.characters["ghost"] = Character(key="ghost", name="Ghost", role="ghost")
    st.main_character_id = "ghost"

    sysmsg = pb.system_prompt(st)
    assert "### CHARACTER IDENTITY" in sysmsg
    assert "- You are a ghost." in sysmsg
    assert "- You died in this apartment." in sysmsg
    assert "speak them directly in first person" in sysmsg


def test_character_identity_section_absent_when_not_defined():
    """No CHARACTER IDENTITY section when story_cfg has no character_self_knowledge."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["npc"] = Character(key="npc", name="NPC", role="guard")
    st.main_character_id = "npc"

    sysmsg = pb.system_prompt(st)
    assert "### CHARACTER IDENTITY" not in sysmsg
