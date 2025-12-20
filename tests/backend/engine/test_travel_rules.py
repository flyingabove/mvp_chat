 # tests/backend/engine/world/test_travel_rules.py
from backend.app.engine.world.travel_rules import TravelRules
from backend.app.engine.world.edge import PathEdge


def test_choose_edge_deterministic():
    rules = TravelRules(seed=42)

    edges = [
        PathEdge("a", "b", 5),
        PathEdge("a", "c", 6),
    ]

    chosen = rules.choose_edge(edges)
    assert chosen in edges


def test_choose_edge_ignores_blocked():
    rules = TravelRules(seed=1)

    edges = [
        PathEdge("a", "b", 5, blocked=True),
        PathEdge("a", "c", 6, blocked=False),
    ]

    chosen = rules.choose_edge(edges)
    assert chosen.to_id == "c"
