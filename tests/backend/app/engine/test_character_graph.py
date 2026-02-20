# tests/backend/app/engine/test_character_graph.py
"""Character relationship graph tests."""

from backend.app.engine.character_graph import (
    CharacterGraph,
    RelationshipEdge,
    RelationshipState,
    RelationshipType,
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
    assert "Trust:" in output
    assert "Fear:" in output


def test_format_for_prompt_empty_graph():
    cg = CharacterGraph.from_dict(None)
    output = cg.format_for_prompt("iu", {})
    assert output == ""
