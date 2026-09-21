import json
import math
from pathlib import Path

import pytest

from backend.app.engine.world.edge import PathEdge
from backend.app.engine.world.graph import WorldGraph
from backend.app.engine.world.ids import LocationId
from backend.app.engine.world.location import Location
from backend.app.engine.world.map_model import WorldMap, world_map_payload
from backend.app.engine.world.travel_rules import TravelBlockedError, TravelRules
from backend.app.engine.world.world_json import WorldDefinitionLoader
from backend.app.engine.world.world_loader import WorldLoader

ROOT = Path(__file__).resolve().parents[5]
WORLD = ROOT / "backend/app/stories/7_six_strangers/six_strangers_world.json"


def load_graph():
    return WorldLoader.load_from_file(str(WORLD)).world_graph


def test_inventory_is_complete_atomic_and_deduplicated():
    graph = load_graph()
    source_ids = [
        sid for loc in graph.locations.values() for sid in loc.research.source_ids
    ]
    expected = {
        f"{prefix}{i:02}"
        for prefix, count in (("H", 18), ("E", 67), ("O", 15))
        for i in range(1, count + 1)
    }
    assert set(source_ids) == expected
    assert len(source_ids) == len(expected)
    assert len(graph.locations) == 103
    assert set(graph.locations).isdisjoint(a.id for a in graph.world_map.areas)
    assert graph.get_location("swimming_pool").research.source_ids == ("H15", "O13")
    assert graph.get_location("terrace").name == "Terrace / Pool Deck"
    assert graph.get_location("player_bedroom").research.status == "game_added"


def test_regional_distance_bands_and_directions():
    atlas = load_graph().world_map
    areas = {a.id: a for a in atlas.areas}
    for a in areas.values():
        if a.position and a.distance_min_km is not None:
            assert (
                a.distance_min_km - 0.01
                <= math.hypot(a.position.x, a.position.y)
                <= a.distance_max_km + 0.01
            )
    assert areas["takao"].position.x == -43
    assert areas["odaiba"].position.x == 8
    assert areas["enoshima"].position.x < areas["kamakura"].position.x < 0
    assert areas["nagatoro"].position.x < 0 < areas["nagatoro"].position.y
    assert areas["unverified"].position is None
    assert areas["cup_noodles_museum"].parent_id == "yokohama"


def test_all_places_reachable_without_fabricated_edges():
    graph = load_graph()
    rules = TravelRules(seed=7)
    before = sum(len(graph.get_neighbors(lid)) for lid in graph.locations)
    # Test all destinations from home and from the most distant regional endpoint.
    for origin in ("front_entry", "place_e59"):
        for lid in graph.locations:
            route = rules.resolve_route(graph, LocationId(origin), LocationId(lid))
            assert all(not s.edge.blocked for s in route.segments)
            if lid != origin:
                assert route.total_transit_minutes() > 0
    assert before == sum(len(graph.get_neighbors(lid)) for lid in graph.locations)
    destinations = ["place_e01", "place_e48", "place_e23", "place_e05", "place_e58"]
    durations = [
        rules.resolve_route(
            graph, LocationId("front_entry"), LocationId(lid)
        ).total_transit_minutes()
        for lid in destinations
    ]
    assert durations == sorted(durations)
    # Summit cannot use an eight-minute generic intra-cluster shortcut.
    assert (
        rules.resolve_route(
            graph, LocationId("place_e19"), LocationId("place_e20")
        ).total_transit_minutes()
        == 60
    )
    museum = rules.resolve_route(
        graph, LocationId("gotanda_station"), LocationId("place_e49")
    )
    assert [s.edge.to_id.value for s in museum.segments] == ["place_e48", "place_e49"]


def test_both_loaders_preserve_map_metadata_and_routes():
    graph = load_graph()
    other = (
        WorldDefinitionLoader()
        .from_dict(json.loads(WORLD.read_text(encoding="utf-8")))
        .graph
    )
    assert world_map_payload(graph) == world_map_payload(other)
    payload = world_map_payload(graph)
    assert len(payload["locations"]) == 103
    assert all(e["estimated"] for e in payload["routes"])


def test_map_validation_rejects_bad_geometry_and_parent_cycles():
    with pytest.raises(ValueError):
        WorldMap.from_dict(
            {
                "areas": [
                    {
                        "id": "a",
                        "name": "A",
                        "position": {"x": 100, "y": 0},
                        "distance_min_km": 1,
                        "distance_max_km": 2,
                    }
                ]
            }
        )
    with pytest.raises(ValueError):
        WorldMap.from_dict(
            {
                "areas": [
                    {"id": "a", "name": "A", "parent_id": "b"},
                    {"id": "b", "name": "B", "parent_id": "a"},
                ]
            }
        )
    with pytest.raises(ValueError):
        WorldMap().validate_locations({"x": Location("x", "X", "", area_id="missing")})


def test_opt_in_shortest_time_policy_respects_blocks_and_disconnected_worlds():
    graph = WorldGraph(WorldMap(route_policy="shortest_time"))
    for lid in ("a", "b", "c", "d"):
        graph.add_location(Location(lid, lid, ""))
    graph.add_edge(PathEdge("a", "b", 90))
    graph.add_edge(PathEdge("a", "c", 5))
    graph.add_edge(PathEdge("c", "b", 5))
    graph.add_edge(PathEdge("b", "d", 5, blocked=True))
    rules = TravelRules(1)
    assert (
        rules.resolve_route(
            graph, LocationId("a"), LocationId("b")
        ).total_transit_minutes()
        == 10
    )
    with pytest.raises(TravelBlockedError):
        rules.resolve_route(graph, LocationId("a"), LocationId("d"))
    with pytest.raises(ValueError, match="No authored route"):
        rules.resolve_route(graph, LocationId("c"), LocationId("a"))


def test_legacy_world_and_story_metadata_still_load():
    from backend.app.api.story import get_story_meta

    old = WorldLoader.load_from_file(
        str(
            ROOT
            / "backend/app/stories/1_iu_murder_mystery/iu_murder_mystery_world.json"
        )
    )
    assert old.world_graph.world_map.route_policy == "legacy"
    meta = get_story_meta("six_strangers")
    assert len(meta["known_locations"]) == 103
    assert len(meta["world_map"]["areas"]) == 25


def test_extractor_includes_destinations_after_eightieth_node():
    from backend.app.engine.extractors.location_extractor import LocationExtractor

    block = LocationExtractor._build_locations_block(load_graph())
    assert "place_o15:" in block
    assert "dance_studio:" in block
