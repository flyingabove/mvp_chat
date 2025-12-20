import pytest

from app.engine.world.graph import WorldGraph
from app.engine.world.location import Location
from app.engine.world.edge import PathEdge


def test_graph_add_location_and_edge_and_neighbors():
    g = WorldGraph()
    a = Location(id="A", name="A", description="", tags=[])
    b = Location(id="B", name="B", description="", tags=[])
    g.add_location(a)
    g.add_location(b)

    e = PathEdge(from_id="A", to_id="B", minutes=5)
    g.add_edge(e)

    neigh = g.get_neighbors("A")
    assert neigh and neigh[0].to_id == "B"


def test_graph_rejects_duplicate_location_ids():
    g = WorldGraph()
    g.add_location(Location(id="A", name="A", description="", tags=[]))
    with pytest.raises(ValueError):
        g.add_location(Location(id="A", name="A2", description="", tags=[]))


def test_graph_rejects_edges_with_unknown_nodes():
    g = WorldGraph()
    g.add_location(Location(id="A", name="A", description="", tags=[]))
    with pytest.raises(KeyError):
        g.add_edge(PathEdge(from_id="A", to_id="B", minutes=1))