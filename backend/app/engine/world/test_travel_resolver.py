import pytest

from backend.app.engine.world.clock import WorldClock
from backend.app.engine.world.edge import PathEdge
from backend.app.engine.world.exposure import TravelExposure
from backend.app.engine.world.graph import WorldGraph
from backend.app.engine.world.location import Location
from backend.app.engine.world.travel_resolver import TravelResolver
from backend.app.engine.world.travel_rules import TravelRules


class _StubExposureResolver:
    def __init__(self):
        self.calls = []

    def roll(self, intermediate_id=None):
        self.calls.append(intermediate_id)
        return TravelExposure(
            exit_event=False,
            pass_intermediate=False,
            event_at_intermediate=False,
            enter_event=False,
            describe_destination=True,
            intermediate_id=None,
        )


def test_travel_resolver_should_only_consider_edges_to_destination():
    g = WorldGraph()
    g.add_location(Location(id="A", name="A", description="", tags=[]))
    g.add_location(Location(id="B", name="B", description="", tags=[]))
    g.add_location(Location(id="C", name="C", description="", tags=[]))
    g.add_edge(PathEdge(from_id="A", to_id="B", minutes=5))
    g.add_edge(PathEdge(from_id="A", to_id="C", minutes=99))

    clock = WorldClock()
    rules = TravelRules(seed=0)
    exp = _StubExposureResolver()
    tr = TravelResolver(g, clock, rules, exp)

    tr.resolve("A", "B")
    # Expected: only 5 mins transit; actual may select 99 mins if bug triggers.
    assert clock.minute == 1 + 5


def test_travel_resolver_advances_time_and_calls_exposure():
    g = WorldGraph()
    g.add_location(Location(id="A", name="A", description="", tags=[]))
    g.add_location(Location(id="B", name="B", description="", tags=[]))
    g.add_edge(PathEdge(from_id="A", to_id="B", minutes=5))

    clock = WorldClock()
    rules = TravelRules(seed=0)
    exp = _StubExposureResolver()
    tr = TravelResolver(g, clock, rules, exp)

    exposure = tr.resolve("A", "B")
    assert exposure.describe_destination is True
    assert clock.minute == 1 + 5
    assert exp.calls == [None]