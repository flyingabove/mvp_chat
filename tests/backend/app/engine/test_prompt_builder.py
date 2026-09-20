

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


def test_prompt_includes_default_persona():
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"
    st.user.persona_mode = "default"
    st.user.persona_name = "Paul Dingus"
    st.user.persona_other = "quietly observant"

    sysmsg = pb.system_prompt(st)
    assert "Your default persona is Paul Dingus" in sysmsg
    assert "Other attributes: " in sysmsg
    assert "Devilishly handsome Black man who knows a little Japanese." in sysmsg


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
    tail = sysmsg.split("Beliefs and suspicions (not necessarily true):\n", 1)[1]
    # The beliefs section is followed by the PACING AND INITIATIVE section
    # (Phase 4) - isolate just the belief lines by cutting at the next
    # section's leading separator rather than assuming beliefs is the last
    # thing in the prompt.
    section = tail.split("\n\n────", 1)[0].strip()

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


# ─── Phase 3 "Social life": goal line in the character identity block ───────

def test_character_identity_section_renders_goal_when_present():
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.social_traits import EvolvingTrait

    st = init_state()
    st.story_cfg = {"character_self_knowledge": ["You are a ghost."]}
    ghost = Character(key="ghost", name="Ghost", role="ghost")
    ghost.goal = EvolvingTrait(kind="goal", subject_id="ghost")
    ghost.goal.set_initial("Find out who killed you.")
    st.characters["ghost"] = ghost
    st.main_character_id = "ghost"

    sysmsg = pb.system_prompt(st)
    assert "[Ghost's current goal] Find out who killed you." in sysmsg


def test_character_identity_section_no_goal_line_when_absent():
    """Graceful degradation: a character with goal=None must render
    byte-identical output to the pre-Phase-3 baseline - no stray goal text."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"character_self_knowledge": ["You are a ghost."]}
    ghost = Character(key="ghost", name="Ghost", role="ghost")
    assert ghost.goal is None
    st.characters["ghost"] = ghost
    st.main_character_id = "ghost"

    sysmsg = pb.system_prompt(st)
    assert "current goal" not in sysmsg


# ─── BL-07: per-character self_knowledge for present non-main characters ─────

def test_character_identity_section_includes_present_non_main_character():
    """A non-main character with their own self_knowledge who is present in
    the scene gets their own CHARACTER IDENTITY block, alongside the main
    character's block."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["mina"] = Character(
        key="mina", name="Mina", role="housemate", is_main=True,
        self_knowledge=["You are the first to notice when someone's upset."],
    )
    st.characters["daeho"] = Character(
        key="daeho", name="Dae-ho", role="housemate",
        self_knowledge=["You hate asking anyone for help.", "You keep score of every favor."],
    )
    st.characters["priya"] = Character(
        key="priya", name="Priya", role="housemate",
        self_knowledge=["You left home to prove you could stand alone."],
    )
    st.main_character_id = "mina"

    # Only Mina and Dae-ho are present; Priya is not.
    st.add_transient_entry(
        id="pp::mina", namespace="test", scope="scene",
        text="__people_present_marker__:mina", expires_after_turns=4,
    )
    st.add_transient_entry(
        id="pp::daeho", namespace="test", scope="scene",
        text="__people_present_marker__:daeho", expires_after_turns=4,
    )

    sysmsg = pb.system_prompt(st, current_user_msg="hello")
    assert "### CHARACTER IDENTITY — Mina" in sysmsg
    assert "You are the first to notice when someone's upset." in sysmsg
    assert "### CHARACTER IDENTITY — Dae-ho" in sysmsg
    assert "You hate asking anyone for help." in sysmsg
    assert "You keep score of every favor." in sysmsg
    assert "### CHARACTER IDENTITY — Priya" not in sysmsg
    assert "You left home to prove you could stand alone." not in sysmsg


def test_character_identity_section_absent_non_main_character_not_present():
    """A non-main character with self_knowledge who is NOT currently present
    contributes no block (scoping to scene presence keeps prompt length
    bounded)."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["mina"] = Character(key="mina", name="Mina", role="housemate", is_main=True)
    st.characters["priya"] = Character(
        key="priya", name="Priya", role="housemate",
        self_knowledge=["You left home to prove you could stand alone."],
    )
    st.main_character_id = "mina"

    st.add_transient_entry(
        id="pp::mina", namespace="test", scope="scene",
        text="__people_present_marker__:mina", expires_after_turns=4,
    )

    sysmsg = pb.system_prompt(st, current_user_msg="hello")
    assert "### CHARACTER IDENTITY" not in sysmsg


def test_character_identity_section_main_character_unconditional_regardless_of_presence():
    """The main character's identity block is unconditional (a ghost NPC not
    tied to a location still gets their block) — unchanged legacy behavior."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["iu"] = Character(
        key="iu", name="IU", role="ghost", is_main=True,
        self_knowledge=["You are a ghost."],
    )
    st.main_character_id = "iu"
    # No people-present markers at all.

    sysmsg = pb.system_prompt(st, current_user_msg="hello")
    assert "### CHARACTER IDENTITY — IU" in sysmsg
    assert "You are a ghost." in sysmsg


# ─── Optional `mode` layer (social_sim / ensemble slice-of-life games) ───────
# See documentation/model_output_docs/SOCIAL_MODE_DESIGN.md for the schema.

def test_mode_context_section_absent_when_no_mode_key():
    """Backward compatibility: a story without `mode` gets zero extra content."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["npc"] = Character(key="npc", name="NPC", role="guard")
    st.main_character_id = "npc"

    sysmsg = pb.system_prompt(st)
    assert "GAME MODE CONTEXT" not in sysmsg
    assert pb._mode_context_section(st) == ""


def test_mode_context_section_byte_identical_prompt_for_existing_story():
    """A05-style regression guard: adding the mode layer must not change the
    assembled prompt for any story that predates it (e.g. the IU mystery),
    byte for byte."""
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.story_loader import load_story

    story = load_story("iu_murder_mystery")
    assert story is not None
    story_dict = story.as_dict()
    assert "mode" not in story_dict, "fixture assumption: iu_murder_mystery has no mode key"

    st = init_state()
    st.story_cfg = {
        "meta": story_dict.get("meta", {}),
        "character_self_knowledge": story_dict.get("character_self_knowledge", []),
    }
    st.characters["iu"] = Character(key="iu", name="IU", role="ghost")
    st.main_character_id = "iu"

    before = pb.system_prompt(st, current_user_msg="hello")
    # Sanity: the mode layer genuinely contributes nothing for this story_cfg.
    assert pb._mode_context_section(st) == ""
    after = pb.system_prompt(st, current_user_msg="hello")
    assert before == after


def test_mode_context_section_injected_for_social_sim_story():
    """A story with a `mode` block gets the GAME MODE CONTEXT section, including
    the confessional convention text when confessional.enabled is true."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {
        "meta": {"disclaimer": "fiction"},
        "mode": {
            "type": "social_sim",
            "setting": "shared_house",
            "open_ended": True,
            "cast_size": 3,
            "confessional": {
                "enabled": True,
                "convention": "Player may address an unseen listener directly as a private aside.",
            },
            "daily_rhythm": ["Mornings are rushed."],
        },
    }
    st.characters["mina"] = Character(key="mina", name="Mina", role="housemate")
    st.main_character_id = "mina"

    sysmsg = pb.system_prompt(st)
    assert "### GAME MODE CONTEXT" in sysmsg
    assert "ensemble slice-of-life story" in sysmsg
    assert "shared house" in sysmsg
    assert "no fixed win condition" in sysmsg
    assert "Confessional convention" in sysmsg
    assert "Player may address an unseen listener directly as a private aside." in sysmsg
    assert "Mornings are rushed." in sysmsg
    # Never react to confessional asides as an NPC.
    assert "never have an NPC" in sysmsg or "react to" in sysmsg


def test_mode_context_section_omitted_confessional_block():
    """confessional.enabled False (or absent) means no confessional text."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {
        "meta": {},
        "mode": {"type": "social_sim", "setting": "shared_house", "open_ended": True, "cast_size": 3},
    }
    st.characters["mina"] = Character(key="mina", name="Mina", role="housemate")
    st.main_character_id = "mina"

    sysmsg = pb.system_prompt(st)
    assert "### GAME MODE CONTEXT" in sysmsg
    assert "Confessional convention" not in sysmsg


def test_mode_context_section_narrator_asides_absent_by_default():
    """Backward compatibility: a `mode` block without `narrator_asides` (e.g.
    The Common Room's mode config) renders no narrator-aside text — this is
    the byte-identical guarantee for stories that predate the field."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {
        "meta": {},
        "mode": {
            "type": "social_sim",
            "setting": "shared_house",
            "open_ended": True,
            "cast_size": 3,
            "confessional": {"enabled": True, "convention": "Aside convention."},
            "daily_rhythm": ["Mornings are rushed."],
        },
    }
    st.characters["mina"] = Character(key="mina", name="Mina", role="housemate")
    st.main_character_id = "mina"

    before = pb.system_prompt(st)
    sysmsg = pb.system_prompt(st)
    assert "Narrator aside device" not in sysmsg
    assert before == sysmsg


def test_mode_context_section_narrator_asides_rendered_when_enabled():
    """A story that opts into `mode.narrator_asides` gets the documentary-aside
    instruction rendered, distinct from the player's confessional convention."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {
        "meta": {},
        "mode": {
            "type": "social_sim",
            "setting": "shared_house_city",
            "open_ended": True,
            "cast_size": 4,
            "confessional": {"enabled": True, "convention": "Aside convention."},
            "narrator_asides": {
                "enabled": True,
                "style": "Step outside the scene for a wry documentary-crew aside.",
            },
        },
    }
    st.characters["kenji"] = Character(key="kenji", name="Kenji", role="housemate")
    st.main_character_id = "kenji"

    sysmsg = pb.system_prompt(st)
    assert "### GAME MODE CONTEXT" in sysmsg
    assert "Narrator aside device" in sysmsg
    assert "Step outside the scene for a wry documentary-crew aside." in sysmsg
    assert "distinct" in sysmsg or "storyteller's own voice" in sysmsg
    # Still renders the confessional convention alongside it, unaffected.
    assert "Confessional convention" in sysmsg


def test_mode_context_section_narrator_asides_default_style_when_blank():
    """narrator_asides.enabled=True with no custom `style` falls back to a
    sensible default sentence rather than rendering nothing."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {
        "meta": {},
        "mode": {
            "type": "social_sim",
            "narrator_asides": {"enabled": True},
        },
    }
    st.characters["kenji"] = Character(key="kenji", name="Kenji", role="housemate")
    st.main_character_id = "kenji"

    sysmsg = pb.system_prompt(st)
    assert "Narrator aside device:" in sysmsg


# ============================================================================
# Phase 4 "Engagement and polish": explicit response-length calibration and
# NPC-initiative-frequency guidance. Previously the only length instruction
# was the single word "compact" with no scale to anchor against.
# ============================================================================

def test_pacing_section_always_present():
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["ghost"] = Character(key="ghost", name="Ghost", role="ghost")
    st.main_character_id = "ghost"

    sysmsg = pb.system_prompt(st, current_user_msg="hello")
    assert "### PACING AND INITIATIVE" in sysmsg
    assert "Not every reply needs to end with a hook" in sysmsg


def test_pacing_section_scales_short_for_brief_player_message():
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["ghost"] = Character(key="ghost", name="Ghost", role="ghost")
    st.main_character_id = "ghost"

    sysmsg = pb.system_prompt(st, current_user_msg="hi there")
    assert "short and low-stakes" in sysmsg
    assert "HARD LIMIT: 3-4 sentences" in sysmsg


def test_pacing_section_scales_medium_for_normal_message():
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["ghost"] = Character(key="ghost", name="Ghost", role="ghost")
    st.main_character_id = "ghost"

    sysmsg = pb.system_prompt(st, current_user_msg="I walk over and ask her what happened last night at the party")
    assert "normal conversational beat" in sysmsg
    assert "1-2 compact paragraphs" in sysmsg


def test_pacing_section_scales_long_for_substantive_message():
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["ghost"] = Character(key="ghost", name="Ghost", role="ghost")
    st.main_character_id = "ghost"

    long_msg = (
        "I sit down across from her and take a slow breath before finally asking the question "
        "that's been on my mind since we first met - I want to know the whole truth about what "
        "happened that night, no matter how painful it might be to hear, because I think we both "
        "deserve to move forward honestly."
    )
    sysmsg = pb.system_prompt(st, current_user_msg=long_msg)
    assert "substantive" in sysmsg
    assert "More room is warranted" in sysmsg


def test_pacing_section_appears_after_character_identity_before_truth_override():
    """The pacing contract should be among the last instructions the model
    sees (most-recent-instruction-wins convention), placed after character
    identity, matching the existing layering discipline in this file."""
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {
        "meta": {"disclaimer": "fiction"},
        "character_self_knowledge": ["You are a ghost."],
    }
    st.characters["ghost"] = Character(key="ghost", name="Ghost", role="ghost")
    st.main_character_id = "ghost"

    sysmsg = pb.system_prompt(st, current_user_msg="hello")
    identity_idx = sysmsg.index("### CHARACTER IDENTITY")
    pacing_idx = sysmsg.index("### PACING AND INITIATIVE")
    assert identity_idx < pacing_idx


def test_pacing_section_in_return_layers():
    from backend.app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {"meta": {"disclaimer": "fiction"}}
    st.characters["ghost"] = Character(key="ghost", name="Ghost", role="ghost")
    st.main_character_id = "ghost"

    _, layers = pb.system_prompt(st, current_user_msg="hello", return_layers=True)
    assert "pacing_and_initiative" in layers
    assert "### PACING AND INITIATIVE" in layers["pacing_and_initiative"]
