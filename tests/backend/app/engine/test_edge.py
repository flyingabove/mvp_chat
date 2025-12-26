from backend.app.engine.world.edge import PathEdge


def test_edge_is_immutable_dataclass():
    e = PathEdge(from_id="a", to_id="b", minutes=3, is_transit=True)
    assert e.from_id == "a"
    assert e.to_id == "b"
    assert e.minutes == 3
    assert e.is_transit is True