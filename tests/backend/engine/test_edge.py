# tests/backend/engine/world/test_edge.py
from backend.app.engine.world.edge import PathEdge


def test_edge_properties():
    edge = PathEdge(
        from_id="a",
        to_id="b",
        minutes=5,
        is_transit=True,
        blocked=False,
    )

    assert edge.from_id == "a"
    assert edge.to_id == "b"
    assert edge.minutes == 5
    assert edge.is_transit is True
    assert edge.blocked is False
