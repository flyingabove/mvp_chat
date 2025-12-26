import pytest

from backend.app.engine.world.edge import PathEdge
from backend.app.engine.world.travel_rules import TravelRules


def test_choose_edge_filters_blocked_and_is_deterministic():
    rules = TravelRules(seed=1)
    e1 = PathEdge(from_id="A", to_id="B", minutes=5, blocked=True)
    e2 = PathEdge(from_id="A", to_id="C", minutes=7, blocked=False)
    chosen = rules.choose_edge([e1, e2])
    assert chosen == e2

    with pytest.raises(RuntimeError):
        rules.choose_edge([PathEdge(from_id="A", to_id="B", minutes=1, blocked=True)])