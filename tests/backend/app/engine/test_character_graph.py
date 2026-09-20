# tests/backend/app/engine/test_character_graph.py
"""Character relationship graph tests."""

from types import SimpleNamespace

from backend.app.engine.character_graph import (
    CharacterGraph,
    RelationshipEdge,
    RelationshipState,
    RelationshipType,
    _compute_prejudice_state,
    describe_relationship_state,
)
from backend.app.engine.social_traits import EvolvingTrait


# ---------------------------------------------------------------------------
# RelationshipState
# ---------------------------------------------------------------------------

def test_relationship_state_clamps_values():
    rs = RelationshipState(trust=5.0, fear=-1.0, affection=2.0, suspicion=-3.0)
    assert rs.trust == 1.0
    assert rs.fear == 0.0
    assert rs.affection == 1.0
    assert rs.suspicion == 0.0


def test_relationship_state_collapse_to_legacy():
    rs = RelationshipState(trust=0.5, fear=0.1, affection=0.8, suspicion=0.2)
    score = rs.collapse()
    assert -5 <= score <= 5


def test_relationship_state_apply_delta():
    rs = RelationshipState(trust=0.0)
    rs.apply_delta(trust=0.3, fear=0.1)
    assert abs(rs.trust - 0.3) < 0.001
    assert abs(rs.fear - 0.1) < 0.001


def test_relationship_state_from_dict():
    rs = RelationshipState.from_dict({"trust": 0.5, "fear": 0.3})
    assert abs(rs.trust - 0.5) < 0.001
    assert abs(rs.fear - 0.3) < 0.001
    assert rs.affection == 0.0


def test_relationship_state_from_dict_none_safe():
    rs = RelationshipState.from_dict(None)
    assert rs.trust == 0.0


# ---------------------------------------------------------------------------
# RelationshipEdge
# ---------------------------------------------------------------------------

def test_relationship_edge_from_dict():
    edge = RelationshipEdge.from_dict("e1", {
        "from": "iu",
        "to": "player",
        "type": "FRIEND",
        "state": {"trust": 0.5},
        "label": "A friend",
    })
    assert edge.from_id == "iu"
    assert edge.to_id == "player"
    assert edge.type == RelationshipType.FRIEND
    assert abs(edge.state.trust - 0.5) < 0.001
    assert edge.label == "A friend"


def test_relationship_edge_invalid_type_defaults():
    edge = RelationshipEdge.from_dict("e1", {"from": "a", "to": "b", "type": "BOGUS"})
    assert edge.type == RelationshipType.OTHER


# ---------------------------------------------------------------------------
# CharacterGraph
# ---------------------------------------------------------------------------

def test_character_graph_from_dict_list_format():
    cg = CharacterGraph.from_dict({
        "edges": [
            {"id": "e1", "from": "a", "to": "b", "type": "FRIEND"},
            {"id": "e2", "from": "b", "to": "a", "type": "FRIEND"},
        ],
    })
    assert len(cg.edges) == 2


def test_character_graph_from_dict_dict_format():
    cg = CharacterGraph.from_dict({
        "edges": {
            "e1": {"from": "a", "to": "b"},
            "e2": {"from": "a", "to": "c"},
        },
    })
    assert len(cg.edges) == 2


def test_character_graph_from_dict_none_safe():
    cg = CharacterGraph.from_dict(None)
    assert len(cg.edges) == 0


def test_get_edges_from():
    cg = CharacterGraph.from_dict({
        "edges": {
            "e1": {"from": "a", "to": "b"},
            "e2": {"from": "a", "to": "c"},
            "e3": {"from": "b", "to": "a"},
        },
    })
    edges = cg.get_edges_from("a")
    assert len(edges) == 2


def test_get_edge_direct():
    cg = CharacterGraph.from_dict({
        "edges": [{"id": "e1", "from": "a", "to": "b", "type": "ENEMY"}],
    })
    edge = cg.get_edge("a", "b")
    assert edge is not None
    assert edge.type == RelationshipType.ENEMY


def test_get_edge_symmetric_lookup():
    cg = CharacterGraph.from_dict({
        "edges": [{"id": "e1", "from": "a", "to": "b", "symmetric": True}],
    })
    assert cg.get_edge("b", "a") is not None


def test_get_edge_not_found():
    cg = CharacterGraph.from_dict({
        "edges": [{"id": "e1", "from": "a", "to": "b"}],
    })
    assert cg.get_edge("b", "a") is None


def test_apply_rel_delta_backward_compat():
    cg = CharacterGraph.from_dict({
        "edges": [{"id": "e1", "from": "iu", "to": "player", "type": "OTHER"}],
    })
    edge = cg.get_edge("iu", "player")
    assert edge.state.affection == 0.0
    cg.apply_rel_delta("iu", "player", 1)
    assert abs(edge.state.affection - 0.1) < 0.001
    cg.apply_rel_delta("iu", "player", -1)
    assert abs(edge.state.affection - 0.0) < 0.001


def test_apply_rel_delta_missing_edge_no_error():
    cg = CharacterGraph.from_dict(None)
    cg.apply_rel_delta("nobody", "nobody", 1)  # should not raise


def test_format_for_prompt_output():
    cg = CharacterGraph.from_dict({
        "edges": [
            {
                "id": "e1",
                "from": "iu",
                "to": "player",
                "type": "OTHER",
                "state": {"trust": -0.3, "fear": 0.7},
                "label": "The detective interrogating you.",
            },
        ],
    })

    class FakeChar:
        name = "Steve"

    output = cg.format_for_prompt("iu", {"player": FakeChar()})
    assert "player" in output.lower() or "detective" in output.lower()
    assert "Behavior tendency:" in output
    assert "Trust is" in output
    assert "fear is" in output


def test_format_for_prompt_empty_graph():
    cg = CharacterGraph.from_dict(None)
    output = cg.format_for_prompt("iu", {})
    assert output == ""


def test_format_for_prompt_no_disposition_renders_no_disposition_line():
    """Phase 3 'Social life' graceful degradation: an edge with no
    disposition established yet must render byte-identical output to the
    pre-Phase-3 baseline - no stray '[Disposition]' text."""
    cg = CharacterGraph.from_dict({
        "edges": [
            {"id": "e1", "from": "iu", "to": "player", "type": "OTHER", "label": "The detective interrogating you."},
        ],
    })

    class FakeChar:
        name = "Steve"

    output = cg.format_for_prompt("iu", {"player": FakeChar()})
    assert "[Disposition]" not in output


def test_format_for_prompt_renders_disposition_when_present():
    cg = CharacterGraph.from_dict({
        "edges": [
            {"id": "e1", "from": "makoto", "to": "mizuki", "type": "OTHER"},
        ],
    })
    edge = cg.get_edge("makoto", "mizuki")
    edge.disposition = EvolvingTrait(kind="disposition", subject_id="makoto", target_id="mizuki")
    edge.disposition.set_initial("aggressive toward Mizuki", minute=0)

    class FakeChar:
        name = "Mizuki"

    output = cg.format_for_prompt("makoto", {"mizuki": FakeChar()})
    assert "[Disposition] aggressive toward Mizuki" in output


def test_format_for_prompt_filters_by_active_characters():
    """Only edges targeting active characters should appear."""
    cg = CharacterGraph.from_dict({
        "edges": [
            {"id": "e1", "from": "iu", "to": "player", "type": "OTHER"},
            {"id": "e2", "from": "iu", "to": "bob", "type": "FRIEND"},
            {"id": "e3", "from": "iu", "to": "carol", "type": "ENEMY"},
        ],
    })

    class FakeChar:
        name = "Placeholder"

    chars = {"player": FakeChar(), "bob": FakeChar(), "carol": FakeChar()}

    # Only player is active
    output = cg.format_for_prompt("iu", chars, active_characters={"player"})
    assert "player" in output.lower()
    assert "bob" not in output.lower()
    assert "carol" not in output.lower()


def test_format_for_prompt_no_filter_when_none():
    """When active_characters=None, all edges appear (backward compat)."""
    cg = CharacterGraph.from_dict({
        "edges": [
            {"id": "e1", "from": "iu", "to": "player", "type": "OTHER"},
            {"id": "e2", "from": "iu", "to": "bob", "type": "FRIEND"},
        ],
    })

    class FakeChar:
        name = "X"

    chars = {"player": FakeChar(), "bob": FakeChar()}

    output = cg.format_for_prompt("iu", chars, active_characters=None)
    assert "player" in output.lower()
    assert "bob" in output.lower()


def test_format_for_prompt_active_filter_empty_returns_empty():
    """If active set excludes all edge targets, return empty string."""
    cg = CharacterGraph.from_dict({
        "edges": [
            {"id": "e1", "from": "iu", "to": "bob", "type": "FRIEND"},
        ],
    })

    class FakeChar:
        name = "Bob"

    output = cg.format_for_prompt("iu", {"bob": FakeChar()}, active_characters={"player"})
    assert output == ""


def test_describe_relationship_state_normalizes_all_dimensions_to_minus1_to_1():
    state = RelationshipState(trust=0.4, fear=0.0, affection=-0.2, suspicion=1.0)
    described = describe_relationship_state(state)
    assert described["trust_normalized"] == 0.4
    assert described["fear_normalized"] == -1.0
    assert described["affection_normalized"] == -0.2
    assert described["suspicion_normalized"] == 1.0


def test_describe_relationship_state_returns_deterministic_words():
    state = RelationshipState(trust=-0.5, fear=0.8, affection=0.3, suspicion=0.2)
    described = describe_relationship_state(state)
    assert described["trust_word"] == "skeptical"
    assert described["fear_word"] == "terrified"
    assert described["affection_word"] == "fond"
    assert described["suspicion_word"] == "unconcerned"


# ---------------------------------------------------------------------------
# First-meeting detection + prejudice initialization
# ---------------------------------------------------------------------------

def _make_char(key, role="", is_suspect=False, tags=None, name=None):
    """Minimal Character-like object for prejudice tests."""
    return SimpleNamespace(
        key=key,
        name=name or key.title(),
        role=role,
        is_suspect=is_suspect,
        tags=tags or [],
    )


def _make_state(canonical_facts=None):
    """Minimal GameState-like object exposing only canonical_facts."""
    return SimpleNamespace(canonical_facts=canonical_facts or [])


def _make_fact(text, known_by, subject=""):
    """Minimal KnowledgeChunk-like object for prejudice fact scanning."""
    return SimpleNamespace(text=text, content=text, known_by=known_by, subject=subject)


def _make_graph_with_edge(from_id, to_id, met_at=None):
    """Build a CharacterGraph with a single authored edge."""
    cg = CharacterGraph.from_dict({
        "edges": [{"id": "e1", "from": from_id, "to": to_id}],
    })
    if met_at is not None:
        cg.get_edge(from_id, to_id).met_at = met_at
    return cg


def test_first_meeting_marks_met_at_on_existing_edge():
    """Authored edge with met_at=None gets stamped on process_first_meetings."""
    cg = _make_graph_with_edge("iu", "player")
    a = _make_char("iu")
    b = _make_char("player")
    cg.add_character(a)
    cg.add_character(b)

    state = _make_state()
    cg.process_first_meetings(room_ids={"iu", "player"}, state=state, current_minute=5)

    edge = cg.get_edge("iu", "player")
    assert edge.met_at == 5


def test_first_meeting_skips_pair_if_already_met():
    """If met_at is already set, process_first_meetings does not overwrite it."""
    cg = _make_graph_with_edge("iu", "player", met_at=3)
    a = _make_char("iu")
    b = _make_char("player")
    cg.add_character(a)
    cg.add_character(b)

    state = _make_state()
    cg.process_first_meetings(room_ids={"iu", "player"}, state=state, current_minute=10)

    edge = cg.get_edge("iu", "player")
    assert edge.met_at == 3  # unchanged


def test_first_meeting_creates_edge_when_none_exists():
    """When no authored edge exists, process_first_meetings creates one."""
    cg = CharacterGraph()
    a = _make_char("iu")
    b = _make_char("steve")
    cg.add_character(a)
    cg.add_character(b)

    state = _make_state()
    assert cg.get_edge("iu", "steve") is None

    cg.process_first_meetings(room_ids={"iu", "steve"}, state=state, current_minute=7)

    edge = cg.get_edge("iu", "steve")
    assert edge is not None
    assert edge.met_at == 7
    assert edge.from_id == "iu"
    assert edge.to_id == "steve"


def test_met_before_game_json_flag_sets_met_at_zero():
    """from_dict with met_before_game=true → met_at = 0 at load time."""
    cg = CharacterGraph.from_dict({
        "edges": [{"id": "e1", "from": "iu", "to": "player", "met_before_game": True}],
    })
    edge = cg.get_edge("iu", "player")
    assert edge.met_at == 0


def test_prejudice_suspect_flag_raises_suspicion():
    """b_char.is_suspect=True → A's suspicion toward B is above zero."""
    a = _make_char("detective")
    b = _make_char("steve", is_suspect=True)
    state = _make_state()

    rs, _ = _compute_prejudice_state(a, b, state)
    assert rs.suspicion > 0.0


def test_prejudice_suspect_flag_lowers_trust():
    """b_char.is_suspect=True → A's trust toward B is below zero."""
    a = _make_char("detective")
    b = _make_char("steve", is_suspect=True)
    state = _make_state()

    rs, _ = _compute_prejudice_state(a, b, state)
    assert rs.trust < 0.0


def test_prejudice_suspect_role_lowers_trust():
    """b_char.role containing 'suspect' → A's trust is below zero."""
    a = _make_char("detective")
    b = _make_char("steve", role="prime suspect")
    state = _make_state()

    rs, _ = _compute_prejudice_state(a, b, state)
    assert rs.trust < 0.0


def test_prejudice_ally_role_raises_trust():
    """b_char.role containing 'ally' → A's trust toward B is above zero."""
    a = _make_char("player")
    b = _make_char("guide", role="trusted ally")
    state = _make_state()

    rs, _ = _compute_prejudice_state(a, b, state)
    assert rs.trust > 0.0
    assert rs.affection > 0.0


def test_prejudice_negative_fact_adjusts_state():
    """Canonical fact with negative keyword that A knows about B → lower trust, higher suspicion."""
    a = _make_char("detective")
    b = _make_char("steve", name="Steve")
    fact = _make_fact(
        text="Steve murdered the victim at the studio.",
        known_by=["detective"],
        subject="steve",
    )
    state = _make_state(canonical_facts=[fact])

    rs, _ = _compute_prejudice_state(a, b, state)
    assert rs.trust < 0.0
    assert rs.suspicion > 0.0


def test_prejudice_positive_fact_adjusts_state():
    """Canonical fact with positive keyword that A knows about B → higher trust."""
    a = _make_char("player")
    b = _make_char("bob", name="Bob")
    fact = _make_fact(
        text="Bob helped the police and protected the witnesses.",
        known_by=["player"],
        subject="bob",
    )
    state = _make_state(canonical_facts=[fact])

    rs, _ = _compute_prejudice_state(a, b, state)
    assert rs.trust > 0.0


def test_prejudice_clamped_within_range():
    """Stacking many negative signals never pushes values out of valid range."""
    a = _make_char("player")
    b = _make_char("villain", role="criminal killer murderer villain", is_suspect=True, tags=["dangerous", "violent"])
    facts = [
        _make_fact("villain killed and murdered and attacked people.", known_by=["player"], subject="villain"),
        _make_fact("villain lied and deceived and threatened witnesses.", known_by=["player"], subject="villain"),
    ]
    state = _make_state(canonical_facts=facts)

    rs, _ = _compute_prejudice_state(a, b, state)
    assert -1.0 <= rs.trust <= 1.0
    assert 0.0 <= rs.fear <= 1.0
    assert -1.0 <= rs.affection <= 1.0
    assert 0.0 <= rs.suspicion <= 1.0
    assert 0.0 <= rs.jealousy <= 1.0


def test_relationship_type_inferred_as_suspect_when_high_suspicion():
    """When computed suspicion >= 0.30, inferred type is SUSPECT."""
    a = _make_char("detective")
    b = _make_char("steve", role="suspect", is_suspect=True)
    state = _make_state()

    _, rel_type = _compute_prejudice_state(a, b, state)
    assert rel_type == RelationshipType.SUSPECT


def test_relationship_type_inferred_as_friend_when_warm():
    """When computed affection >= 0.20 and trust >= 0.10, inferred type is FRIEND.

    Role 'ally' gives trust+0.10, affection+0.10. Two positive facts cap
    each add trust+0.10 affection+0.05, totalling trust=0.30, affection=0.20.
    """
    a = _make_char("player")
    b = _make_char("guide", role="ally", name="Guide")
    facts = [
        _make_fact("guide helped the player through the crisis.", known_by=["player"], subject="guide"),
        _make_fact("guide saved the player from danger.", known_by=["player"], subject="guide"),
    ]
    state = _make_state(canonical_facts=facts)

    _, rel_type = _compute_prejudice_state(a, b, state)
    assert rel_type == RelationshipType.FRIEND


# ---------------------------------------------------------------------------
# Relationship history fields — new in RelationshipEdge
# ---------------------------------------------------------------------------

def test_relationship_edge_history_fields_default_values():
    """New history fields default to safe zero/None/False values."""
    edge = RelationshipEdge.from_dict("e1", {"from": "iu", "to": "player"})
    assert edge.last_met_at is None
    assert edge.meeting_count == 0
    assert edge.prior_relationship is False
    assert edge.prior_intimacy is False
    assert edge.in_relationship is False


def test_relationship_edge_history_fields_from_dict():
    """History fields are parsed from story JSON."""
    edge = RelationshipEdge.from_dict("e1", {
        "from": "iu",
        "to": "steve",
        "met_before_game": True,
        "meeting_count": 25,
        "prior_relationship": True,
        "prior_intimacy": False,
        "in_relationship": True,
    })
    assert edge.met_at == 0            # met_before_game → 0
    assert edge.meeting_count == 25
    assert edge.prior_relationship is True
    assert edge.prior_intimacy is False
    assert edge.in_relationship is True


def test_first_meeting_sets_last_met_at_and_meeting_count():
    """First physical meeting sets last_met_at and meeting_count=1."""
    cg = _make_graph_with_edge("iu", "player")
    cg.add_character(_make_char("iu"))
    cg.add_character(_make_char("player"))

    state = _make_state()
    cg.process_first_meetings(room_ids={"iu", "player"}, state=state, current_minute=10)

    edge = cg.get_edge("iu", "player")
    assert edge.met_at == 10
    assert edge.last_met_at == 10
    assert edge.meeting_count == 1


def test_is_new_encounter_increments_meeting_count():
    """Subsequent encounters with is_new_encounter=True increment meeting_count."""
    cg = _make_graph_with_edge("iu", "player", met_at=5)
    cg.get_edge("iu", "player").last_met_at = 5
    cg.get_edge("iu", "player").meeting_count = 1
    cg.add_character(_make_char("iu"))
    cg.add_character(_make_char("player"))

    state = _make_state()
    cg.process_first_meetings(
        room_ids={"iu", "player"}, state=state, current_minute=20, is_new_encounter=True
    )

    edge = cg.get_edge("iu", "player")
    assert edge.met_at == 5            # first meeting unchanged
    assert edge.last_met_at == 20
    assert edge.meeting_count == 2


def test_not_new_encounter_does_not_increment_meeting_count():
    """When is_new_encounter=False, meeting_count is not changed for already-met pairs."""
    cg = _make_graph_with_edge("iu", "player", met_at=5)
    cg.get_edge("iu", "player").last_met_at = 5
    cg.get_edge("iu", "player").meeting_count = 1
    cg.add_character(_make_char("iu"))
    cg.add_character(_make_char("player"))

    state = _make_state()
    cg.process_first_meetings(
        room_ids={"iu", "player"}, state=state, current_minute=30, is_new_encounter=False
    )

    edge = cg.get_edge("iu", "player")
    assert edge.meeting_count == 1     # unchanged — not a new encounter
    assert edge.last_met_at == 5       # unchanged


def test_new_edge_from_process_first_meetings_has_meeting_count_one():
    """Newly created (unscripted) edges get meeting_count=1 and last_met_at set."""
    cg = CharacterGraph()
    cg.add_character(_make_char("iu"))
    cg.add_character(_make_char("steve"))

    state = _make_state()
    cg.process_first_meetings(room_ids={"iu", "steve"}, state=state, current_minute=15)

    edge = cg.get_edge("iu", "steve")
    assert edge.meeting_count == 1
    assert edge.last_met_at == 15


def test_update_edge_history_sets_fields():
    """update_edge_history applies only the provided non-None fields."""
    cg = _make_graph_with_edge("iu", "player")
    edge = cg.get_edge("iu", "player")
    assert edge.prior_relationship is False
    assert edge.in_relationship is False

    result = cg.update_edge_history("iu", "player", prior_relationship=True, in_relationship=True)

    assert result is True
    assert edge.prior_relationship is True
    assert edge.in_relationship is True
    assert edge.prior_intimacy is False  # not passed → unchanged


def test_update_edge_history_none_does_not_overwrite():
    """update_edge_history with None does not overwrite existing values."""
    cg = _make_graph_with_edge("iu", "player")
    edge = cg.get_edge("iu", "player")
    edge.prior_relationship = True

    cg.update_edge_history("iu", "player", prior_relationship=None)

    assert edge.prior_relationship is True  # None → no change


def test_update_edge_history_missing_edge_returns_false():
    """update_edge_history returns False when the edge doesn't exist."""
    cg = CharacterGraph()
    result = cg.update_edge_history("nobody", "player", in_relationship=True)
    assert result is False


def test_symmetric_edge_copies_history_fields():
    """symmetric=true reverse edge copies all history fields from the forward edge."""
    cg = CharacterGraph.from_dict({
        "edges": [{
            "id": "e1",
            "from": "iu",
            "to": "player",
            "symmetric": True,
            "met_before_game": True,
            "meeting_count": 10,
            "prior_relationship": True,
            "in_relationship": True,
        }],
    })
    fwd = cg.get_edge("iu", "player")
    rev = cg.get_edge("player", "iu")

    assert rev is not None
    assert rev.met_at == fwd.met_at
    assert rev.meeting_count == fwd.meeting_count
    assert rev.prior_relationship == fwd.prior_relationship
    assert rev.in_relationship == fwd.in_relationship


# ---------------------------------------------------------------------------
# TurnExtractor — RelationshipHistoryUpdate parsing
# ---------------------------------------------------------------------------

def test_relationship_history_update_dataclass_defaults():
    """RelationshipHistoryUpdate has correct frozen dataclass defaults."""
    from backend.app.engine.extractors.turn_extractor import RelationshipHistoryUpdate
    u = RelationshipHistoryUpdate(from_id="iu", to_id="player")
    assert u.from_id == "iu"
    assert u.to_id == "player"
    assert u.prior_relationship is None
    assert u.prior_intimacy is None
    assert u.in_relationship is None


def test_turn_extractor_parses_relationship_history_updates():
    """TurnExtractor._parse_json correctly parses relationship_history_updates array."""
    from backend.app.engine.extractors.turn_extractor import TurnExtractor
    import json

    payload = json.dumps({
        "movement": {"intent": "NONE", "destination_id": None, "confidence": 0.0, "destination_text": ""},
        "previous_scene": {"location_id": None, "speakers": []},
        "knowledge_updates": [],
        "relationship_history_updates": [
            {
                "from_id": "iu",
                "to_id": "steve",
                "prior_relationship": True,
                "prior_intimacy": False,
                "in_relationship": None,
            }
        ],
    })

    allowed_locs: set[str] = set()
    allowed_chars = {"iu", "steve"}
    result = TurnExtractor._parse_json(payload, allowed_locs, allowed_chars)

    assert len(result.relationship_history_updates) == 1
    upd = result.relationship_history_updates[0]
    assert upd.from_id == "iu"
    assert upd.to_id == "steve"
    assert upd.prior_relationship is True
    assert upd.prior_intimacy is False
    assert upd.in_relationship is None


def test_turn_extractor_drops_history_updates_with_unknown_character():
    """relationship_history_updates entries with unrecognized character keys are dropped."""
    from backend.app.engine.extractors.turn_extractor import TurnExtractor
    import json

    payload = json.dumps({
        "movement": {"intent": "NONE", "destination_id": None, "confidence": 0.0, "destination_text": ""},
        "previous_scene": {"location_id": None, "speakers": []},
        "knowledge_updates": [],
        "relationship_history_updates": [
            {"from_id": "ghost_nobody", "to_id": "player", "in_relationship": True},
        ],
    })

    result = TurnExtractor._parse_json(payload, set(), {"iu", "steve"})
    # "ghost_nobody" not in allowed_chars and not "player" → dropped
    assert len(result.relationship_history_updates) == 0


def test_turn_extractor_allows_player_in_history_updates():
    """'player' is always a valid target in relationship_history_updates."""
    from backend.app.engine.extractors.turn_extractor import TurnExtractor
    import json

    payload = json.dumps({
        "movement": {"intent": "NONE", "destination_id": None, "confidence": 0.0, "destination_text": ""},
        "previous_scene": {"location_id": None, "speakers": []},
        "knowledge_updates": [],
        "relationship_history_updates": [
            {"from_id": "iu", "to_id": "player", "prior_relationship": True},
        ],
    })

    result = TurnExtractor._parse_json(payload, set(), {"iu"})
    assert len(result.relationship_history_updates) == 1
    assert result.relationship_history_updates[0].prior_relationship is True


# ---------------------------------------------------------------------------
# TurnExtractor — RelationshipStateUpdate parsing
# ---------------------------------------------------------------------------

def _minimal_payload(**extra) -> str:
    """Minimal valid TurnExtractor JSON payload with optional overrides."""
    import json
    base = {
        "movement": {"intent": "NONE", "destination_id": None, "confidence": 0.0, "destination_text": ""},
        "previous_scene": {"location_id": None, "speakers": []},
        "knowledge_updates": [],
        "relationship_history_updates": [],
        "relationship_state_updates": [],
    }
    base.update(extra)
    return json.dumps(base)


def test_relationship_state_update_dataclass_defaults():
    """RelationshipStateUpdate has correct frozen dataclass defaults."""
    from backend.app.engine.extractors.turn_extractor import RelationshipStateUpdate
    u = RelationshipStateUpdate(from_id="player", to_id="mia")
    assert u.from_id == "player"
    assert u.to_id == "mia"
    assert u.trust_delta == 0.0
    assert u.fear_delta == 0.0
    assert u.affection_delta == 0.0
    assert u.suspicion_delta == 0.0
    assert u.jealousy_delta == 0.0
    assert u.reason == ""


def test_turn_extractor_parses_relationship_state_updates():
    """_parse_json correctly parses relationship_state_updates array."""
    from backend.app.engine.extractors.turn_extractor import TurnExtractor
    import json

    payload = json.dumps({
        "movement": {"intent": "NONE", "destination_id": None, "confidence": 0.0, "destination_text": ""},
        "previous_scene": {"location_id": None, "speakers": []},
        "knowledge_updates": [],
        "relationship_history_updates": [],
        "relationship_state_updates": [
            {
                "from_id": "player",
                "to_id": "mia",
                "trust_delta": -0.08,
                "suspicion_delta": 0.07,
                "reason": "player accused mia of lying",
            }
        ],
    })

    result = TurnExtractor._parse_json(payload, set(), {"mia"})
    assert len(result.relationship_state_updates) == 1
    su = result.relationship_state_updates[0]
    assert su.from_id == "player"
    assert su.to_id == "mia"
    assert abs(su.trust_delta - (-0.08)) < 0.001
    assert abs(su.suspicion_delta - 0.07) < 0.001
    assert su.reason == "player accused mia of lying"


def test_turn_extractor_clamps_state_update_deltas():
    """Deltas exceeding 0.10 are clamped to 0.10."""
    from backend.app.engine.extractors.turn_extractor import TurnExtractor
    import json

    payload = json.dumps({
        "movement": {"intent": "NONE", "destination_id": None, "confidence": 0.0, "destination_text": ""},
        "previous_scene": {"location_id": None, "speakers": []},
        "knowledge_updates": [],
        "relationship_history_updates": [],
        "relationship_state_updates": [
            {
                "from_id": "player",
                "to_id": "mia",
                "trust_delta": -0.99,    # way too large — should clamp to -0.10
                "fear_delta": 0.99,      # way too large — should clamp to 0.10
                "affection_delta": 0.50, # too large — should clamp to 0.10
            }
        ],
    })

    result = TurnExtractor._parse_json(payload, set(), {"mia"})
    su = result.relationship_state_updates[0]
    assert su.trust_delta == -0.10, f"Expected -0.10, got {su.trust_delta}"
    assert su.fear_delta == 0.10, f"Expected 0.10, got {su.fear_delta}"
    assert su.affection_delta == 0.10, f"Expected 0.10, got {su.affection_delta}"


def test_turn_extractor_drops_state_update_with_non_player_from_id():
    """relationship_state_updates with from_id != 'player' are dropped."""
    from backend.app.engine.extractors.turn_extractor import TurnExtractor
    import json

    payload = json.dumps({
        "movement": {"intent": "NONE", "destination_id": None, "confidence": 0.0, "destination_text": ""},
        "previous_scene": {"location_id": None, "speakers": []},
        "knowledge_updates": [],
        "relationship_history_updates": [],
        "relationship_state_updates": [
            {
                "from_id": "mia",    # not "player" — should be dropped
                "to_id": "steve",
                "trust_delta": -0.10,
            }
        ],
    })

    result = TurnExtractor._parse_json(payload, set(), {"mia", "steve"})
    assert len(result.relationship_state_updates) == 0, (
        "Extractor should only accept from_id='player' in relationship_state_updates"
    )


def test_turn_extractor_drops_state_update_with_unknown_to_id():
    """relationship_state_updates with unrecognized to_id are dropped."""
    from backend.app.engine.extractors.turn_extractor import TurnExtractor
    import json

    payload = json.dumps({
        "movement": {"intent": "NONE", "destination_id": None, "confidence": 0.0, "destination_text": ""},
        "previous_scene": {"location_id": None, "speakers": []},
        "knowledge_updates": [],
        "relationship_history_updates": [],
        "relationship_state_updates": [
            {
                "from_id": "player",
                "to_id": "unknown_npc",   # not in allowed chars — should be dropped
                "trust_delta": -0.05,
            }
        ],
    })

    result = TurnExtractor._parse_json(payload, set(), {"mia"})
    assert len(result.relationship_state_updates) == 0


def test_turn_extractor_fear_and_suspicion_clamp_non_negative():
    """fear_delta and suspicion_delta can't go below 0 (both are 0..1 scales)."""
    from backend.app.engine.extractors.turn_extractor import TurnExtractor
    import json

    payload = json.dumps({
        "movement": {"intent": "NONE", "destination_id": None, "confidence": 0.0, "destination_text": ""},
        "previous_scene": {"location_id": None, "speakers": []},
        "knowledge_updates": [],
        "relationship_history_updates": [],
        "relationship_state_updates": [
            {
                "from_id": "player",
                "to_id": "mia",
                "fear_delta": -0.50,       # negative — should clamp to 0
                "suspicion_delta": -0.50,  # negative — should clamp to 0
            }
        ],
    })

    result = TurnExtractor._parse_json(payload, set(), {"mia"})
    su = result.relationship_state_updates[0]
    assert su.fear_delta == 0.0, f"fear_delta should be 0.0, got {su.fear_delta}"
    assert su.suspicion_delta == 0.0, f"suspicion_delta should be 0.0, got {su.suspicion_delta}"
