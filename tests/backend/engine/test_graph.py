# tests/backend/engine/world/test_graph.py
import pytest
from backend.app.engine.world.graph import WorldGraph
from backend.app.engine.world.location import Location
from backend.app.engine.world.edge import PathEdge


def test_add_and_get_location():
    graph = WorldGraph()
    loc = Location("a", "A", "desc", ["test"])
    graph.add_location(loc)

    assert graph.get_location("a") == loc


def test_duplicate_location_raises():
    graph = WorldGraph()
    loc = Location("a", "A", "desc", ["test"])
    graph.add_location(loc)

    with pytest.raises(ValueError):
        graph.add_location(loc)


def test_add_edge_requires_known_locations():
    graph = WorldGraph()
    loc_a = Location("a", "A", "desc", ["test"])
    graph.add_location(loc_a)

    with pytest.raises(KeyError):
        graph.add_edge(PathEdge("a", "b", 5))


def test_get_neighbors():
    graph = WorldGraph()
    graph.add_location(Location("a", "A", "desc", []))
    graph.add_location(Location("b", "B", "desc", []))

    edge = PathEdge("a", "b", 5)
    graph.add_edge(edge)

    neighbors = graph.get_neighbors("a")
    assert neighbors == [edge]
