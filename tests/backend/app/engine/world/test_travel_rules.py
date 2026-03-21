import pytest
import logging

from backend.app.engine.world.edge import PathEdge
from backend.app.engine.world.graph import WorldGraph
from backend.app.engine.world.location import Location
from backend.app.engine.world.ids import LocationId
from backend.app.engine.world.travel_rules import TravelRules


def test_choose_edge_filters_blocked_and_is_deterministic():
    rules = TravelRules(seed=1)
    e1 = PathEdge(from_id="A", to_id="B", minutes=5, blocked=True)
    e2 = PathEdge(from_id="A", to_id="C", minutes=7, blocked=False)
    chosen = rules.choose_edge([e1, e2])
    assert chosen == e2

    with pytest.raises(RuntimeError):
        rules.choose_edge([PathEdge(from_id="A", to_id="B", minutes=1, blocked=True)])


def test_resolve_route_uses_bfs_for_multihop_path():
    """Test BFS pathfinding for multi-hop routes (A->C->B)."""
    graph = WorldGraph()
    graph.add_location(Location(id="A", name="A", description="", tags=[]))
    graph.add_location(Location(id="B", name="B", description="", tags=[]))
    graph.add_location(Location(id="C", name="C", description="", tags=[]))
    
    # Add edges: A->C and C->B (but no direct A->B)
    graph.add_edge(PathEdge(from_id="A", to_id="C", minutes=5))
    graph.add_edge(PathEdge(from_id="C", to_id="B", minutes=7))
    
    rules = TravelRules(seed=42)
    route = rules.resolve_route(graph, LocationId("A"), LocationId("B"))
    
    # Should find 2-hop path through C
    assert len(route.segments) == 2
    assert route.segments[0].edge.to_id == LocationId("C")
    assert route.segments[1].edge.from_id == LocationId("C")


def test_resolve_route_creates_dynamic_edge_for_island(caplog):
    """Test that island detection logs error and creates dynamic edge."""
    graph = WorldGraph()
    graph.add_location(Location(id="A", name="A", description="", tags=[]))
    graph.add_location(Location(id="B", name="B", description="", tags=[]))
    # No edges - disconnected island
    
    rules = TravelRules(seed=42)
    
    with caplog.at_level(logging.ERROR):
        route = rules.resolve_route(graph, LocationId("A"), LocationId("B"))
    
    # Should log island detection error
    assert "WORLD GRAPH ISLAND DETECTED" in caplog.text
    
    # Should create dynamic edge as fallback
    assert len(route.segments) == 1
    assert route.segments[0].edge.from_id == LocationId("A")
    assert route.segments[0].edge.to_id == LocationId("B")
    assert route.segments[0].edge.is_transit
    assert 8 <= route.segments[0].edge.minutes <= 25