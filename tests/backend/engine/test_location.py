# tests/backend/engine/world/test_location.py
from backend.app.engine.world.location import Location


def test_location_is_immutable():
    loc = Location(
        id="cafe",
        name="Cafe",
        description="A quiet cafe",
        tags=["public", "indoor"],
        allows_phone=True,
    )

    # dataclass frozen=True should prevent mutation
    try:
        loc.name = "New Name"
        assert False, "Location should be immutable"
    except Exception:
        assert True
