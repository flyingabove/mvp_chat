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
