from backend.app.engine.world.location import Location


def test_location_dataclass_fields():
    loc = Location(id="L1", name="Lobby", description="", tags=["public"], allows_phone=False)
    assert loc.id == "L1"
    assert loc.allows_phone is False