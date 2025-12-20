# tests/backend/engine/world/test_travel_resolver.py
from backend.app.engine.world.graph import WorldGraph
from backend.app.engine.world.location import Location
from backend.app.engine.world.edge import PathEdge
from backend.app.engine.world.clock import WorldClock
from backend.app.engine.world.travel_rules import TravelRules
from backend.app.engine.world.exposure import ExposureResolver
from backend.app.engine.world.travel_resolver import TravelResolver


def test_travel_advances_time_and_returns_exposure():
    graph = WorldGraph()
    graph.add_location(Location("a", "A", "desc", []))
    graph.add_location(Location("b", "B", "desc", []))

    graph.add_edge(PathEdge("a", "b", minutes=5))

    clock = WorldClock(start_minute=0)
    rules = TravelRules(seed=42)

    probs = {
        "p_exit_A": 0.0,
        "p_pass_C": 0.0,
        "p_event_at_C": 0.0,
        "p_enter_B": 0.0,
        "p_describe_B": 0.0,
    }

    exposure_resolver = ExposureResolver(seed=42, probs=probs)
    resolver = TravelResolver(graph, clock, rules, exposure_resolver)

    exposure = resolver.resolve("a", "b")

    # EXIT_ORIGIN (1) + TRANSIT (5)
    assert clock.minute == 6
    assert exposure is not None
