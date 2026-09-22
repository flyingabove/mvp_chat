"""Compile the supplied scene inventory into the reusable world schema.

Run from any directory. The inventory is research data, not an instruction file.
Regional offsets honor its distance bands, not precise private addresses. Travel
minutes and indoor positions are authored gameplay estimates. No web geocoding.
"""

from pathlib import Path
import json
import math
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "documentation/research/terrace_house_bgitc_places.md"
TARGET = ROOT / "backend/app/stories/7_six_strangers/six_strangers_world.json"

# Stable game IDs preserve existing sessions and character starting positions.
HOUSE_IDS = "front_entry living_room dining_room kitchen playroom boys_bedroom girls_bedroom washitsu shared_bathroom washroom toilet laundry hallway terrace swimming_pool barbecue driveway garage".split()
HOUSE_NAMES = [
    "Front Entry / Genkan",
    "Living Room",
    "Dining Room",
    "Open Kitchen",
    "Playroom / TV Room",
    "Boys' Bedroom",
    "Girls' Bedroom",
    "Japanese-style Room / Washitsu",
    "Main Bathroom / Bathing Room",
    "Washroom / Vanity Area",
    "Toilet",
    "Laundry / Utility Area",
    "Hallway and Staircase",
    "Terrace / Pool Deck",
    "Swimming Pool",
    "Barbecue Area",
    "Front Exterior / Driveway",
    "Garage / Car Area",
]
HOUSE_POSITIONS = [
    (15, 70),
    (30, 45),
    (50, 45),
    (70, 45),
    (90, 45),
    (15, 15),
    (40, 15),
    (65, 15),
    (45, 70),
    (60, 70),
    (75, 70),
    (90, 70),
    (50, 30),
    (35, 90),
    (55, 90),
    (75, 90),
    (15, 90),
    (5, 90),
]
# (id, name, distance range in km, bearing clockwise from north, direction).
# Nakameguro has no separate range in the source; its local offset is approximate.
REGIONS = [
    ("house", "The House", 0, 0, 0, ""),
    ("gotanda", "Gotanda Neighborhood", 0, 1, 0, "local"),
    ("meguro_ebisu", "Meguro / Ebisu", 3, 5, 45, "NE"),
    ("nakameguro", "Nakameguro", None, None, 0, "N"),
    ("shibuya_aoyama", "Shibuya / Aoyama", 5, 7, 22.5, "NNE"),
    ("marunouchi_tsukiji", "Marunouchi / Tsukiji", 9, 11, 45, "NE"),
    ("odaiba", "Odaiba", 7, 9, 90, "E"),
    ("asakusa_sumida", "Asakusa / Sumida", 13, 15, 45, "NE"),
    ("yomiuriland", "Yomiuriland", 18, 18, 270, "W"),
    ("yokohama", "Yokohama Waterfront", 21, 21, 202.5, "SSW"),
    ("kamakura", "Kamakura", 36, 36, 202.5, "SSW"),
    ("takao", "Mount Takao", 43, 43, 270, "W"),
    ("enoshima", "Enoshima", 43, 43, 225, "SW"),
    ("nagatoro", "Nagatoro", 85, 85, 315, "NW"),
    ("unverified", "Unverified Locations", None, None, 0, "unknown"),
]
AREA_MEMBERS = {
    "meguro_ebisu": [1, 2],
    "shibuya_aoyama": [3, 8, 11, 12, 16, 37],
    "odaiba": [7, 18],
    "enoshima": [5, 6],
    "asakusa_sumida": [9, 39],
    "nakameguro": [10, 17],
    "marunouchi_tsukiji": [13, 44, 45],
    "takao": [19, 20],
    "kamakura": [23],
    "yomiuriland": [24, 25],
    "yokohama": [33, 34, 48, 49, 57],
    "nagatoro": [58, 59, 60],
}
# Explicit estimated station-to-cluster journeys; these are NOT researched schedules.
TRAVEL = {
    "meguro_ebisu": 20,
    "nakameguro": 25,
    "shibuya_aoyama": 25,
    "marunouchi_tsukiji": 35,
    "odaiba": 40,
    "asakusa_sumida": 45,
    "yomiuriland": 60,
    "yokohama": 45,
    "kamakura": 70,
    "takao": 90,
    "enoshima": 85,
    "nagatoro": 150,
    "unverified": 60,
}


def build():
    rows = {}
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        if re.match(r"\| [HEO]\d{2} \|", line):
            cells = [x.strip() for x in line.strip("|").split("|")]
            rows[cells[0]] = cells[1:]
    assert len(rows) == 100, f"Unexpected inventory size: {len(rows)}"
    locations, edges, areas = {}, [], []
    for aid, name, low, high, bearing, direction in REGIONS:
        point = None
        if low is not None:
            radius = (low + high) / 2
            point = {
                "x": round(radius * math.sin(math.radians(bearing)), 4),
                "y": round(radius * math.cos(math.radians(bearing)), 4),
            }
        if aid == "nakameguro":
            point = {"x": -1.5, "y": 4}
        areas.append(
            {
                "id": aid,
                "name": name,
                "position": point,
                "distance_min_km": low,
                "distance_max_km": high,
                "direction": direction,
                "note": "No defensible map position; individual venues need verification."
                if aid == "unverified"
                else "Cluster-level schematic offset, not a venue address.",
            }
        )

    def add(
        lid,
        name,
        description,
        area,
        sid=None,
        status="game_added",
        episodes="",
        note="",
        position=None,
        tags=None,
    ):
        locations[lid] = {
            "name": name,
            "description": description,
            "tags": tags or ["public"],
            "allows_phone": lid not in {"shared_bathroom", "toilet", "swimming_pool"},
            "uuid": f"default_user-six_strangers-1-{lid}",
            "area_id": area,
            "research": {
                "source_ids": [sid] if sid else [],
                "status": status,
                "episodes": episodes,
                "note": note,
            },
        }
        if position:
            locations[lid]["map_position"] = {"x": position[0], "y": position[1]}

    for i, (lid, name, pos) in enumerate(
        zip(HOUSE_IDS, HOUSE_NAMES, HOUSE_POSITIONS), 1
    ):
        sid = f"H{i:02}"
        add(
            lid,
            name,
            rows[sid][1],
            "house",
            sid,
            "scene_derived",
            note="Functional layout inferred from scenes; not a verified floor plan.",
            position=pos,
            tags=["home", "shared", "outdoor" if i in (14, 15, 16, 17) else "indoor"],
        )
    locations["swimming_pool"]["research"]["source_ids"].append("O13")
    for lid in ("boys_bedroom", "girls_bedroom"):
        locations[lid]["tags"].append("bedroom")
        locations[lid]["description"] += (
            " Knock and wait for an invitation before entering."
        )
    # No guest room: the house holds exactly six residents and the player
    # occupies one of the six gendered resident slots, sharing boys_bedroom or
    # girls_bedroom per cast_lifecycle.player_bedrooms. An "added for the
    # seventh resident" room would contradict that invariant, so none is
    # generated here.
    add(
        "neighborhood",
        "Higashi-Gotanda Streets",
        "Residential streets linking the house, local shops and Gotanda Station.",
        "gotanda",
        note="Game connective location; exact house address not published.",
        tags=["outdoor", "public", "transitional"],
    )
    add(
        "gotanda_station",
        "Gotanda Station",
        "Public ticket gates and concourse used to begin city and regional trips.",
        "gotanda",
        note="Game transit node, not a substitute for the unidentified station in E67.",
        tags=["public", "transitional"],
    )
    add(
        "cafe",
        "Neighborhood Cafe",
        "A fictional local cafe for a coffee or quiet conversation.",
        "gotanda",
        note="Retained game addition; distinct from researched named cafes.",
    )

    # Each researched scene area stays atomic, including multiple rooms in one venue.
    for i in range(1, 68):
        sid = f"E{i:02}"
        title, zone, episodes, note = rows[sid]
        aid = next((a for a, ids in AREA_MEMBERS.items() if i in ids), "unverified")
        lid = "salon" if i == 3 else f"place_e{i:02}"
        uncertain = any(
            word in note.lower()
            for word in (
                "not safely",
                "not reliably",
                "not consistently",
                "not verified",
                "verification",
            )
        )
        status = "unverified" if aid == "unverified" or uncertain else "named"
        # The salon's Shibuya cluster is an approximation, not a researched address.
        if i == 3:
            status = "approximate"
            note += " Shibuya cluster placement is approximate; exact address is not asserted."
        add(
            lid,
            f"{title} — {zone}",
            f"{zone} at {title}. {note}",
            aid,
            sid,
            status,
            episodes,
            note,
        )
    for i in range(1, 16):
        if i == 13:  # source explicitly says this is H15, never a duplicate pool.
            continue
        sid = f"O{i:02}"
        title, note = rows[sid]
        lid = "dance_studio" if i == 5 else f"place_o{i:02}"
        add(
            lid,
            title,
            f"{title}. {note}",
            "gotanda" if i == 2 else "unverified",
            sid,
            "approximate" if i == 2 else "unverified",
            note=note,
        )

    def link(a, b, minutes=1, mode="walk"):
        assert a in locations and b in locations
        for source, target in ((a, b), (b, a)):
            if not any(e["from"] == source and e["to"] == target for e in edges):
                edges.append(
                    {
                        "from": source,
                        "to": target,
                        "minutes": minutes,
                        "mode": mode,
                        "is_transit": mode != "walk",
                        "estimated": True,
                    }
                )

    for a, b in [
        ("driveway", "front_entry"),
        ("driveway", "garage"),
        ("front_entry", "garage"),
        ("front_entry", "hallway"),
        ("front_entry", "living_room"),
        ("hallway", "living_room"),
        ("living_room", "dining_room"),
        ("dining_room", "kitchen"),
        ("living_room", "kitchen"),
        ("hallway", "playroom"),
        ("hallway", "boys_bedroom"),
        ("hallway", "girls_bedroom"),
        ("hallway", "washitsu"),
        ("hallway", "washroom"),
        ("washroom", "shared_bathroom"),
        ("hallway", "toilet"),
        ("washroom", "laundry"),
        ("living_room", "terrace"),
        ("dining_room", "terrace"),
        ("terrace", "swimming_pool"),
        ("terrace", "barbecue"),
        ("driveway", "neighborhood"),
        ("front_entry", "neighborhood"),
        ("garage", "neighborhood"),
    ]:
        link(a, b)
    link("neighborhood", "cafe", 5)
    link("neighborhood", "gotanda_station", 10)
    link("neighborhood", "place_o02", 2)

    # Real scene places serve as route endpoints. Containers never enter the graph.
    # Unknown venues get independent estimated trips, never invented co-location.
    for aid in TRAVEL:
        members = [lid for lid, loc in locations.items() if loc["area_id"] == aid]
        if aid == "unverified":
            for lid in members:
                link(
                    "gotanda_station",
                    lid,
                    20 if lid == "dance_studio" else TRAVEL[aid],
                    "estimated_transit",
                )
        elif members:
            for index, lid in enumerate(members):
                link("gotanda_station", lid, TRAVEL[aid], "train_walk")
                for other in members[index + 1 :]:
                    link(lid, other, 15, "walk")
    # Separate zones in one venue are connected by short internal routes.
    for a, b, minutes, mode in [
        (14, 15, 2, "walk"),
        (19, 20, 60, "hike"),
        (24, 25, 5, "walk"),
        (26, 27, 5, "walk"),
        (42, 43, 2, "walk"),
        (44, 45, 2, "walk"),
        (48, 49, 2, "walk"),
        (50, 51, 1, "walk"),
        (52, 53, 2, "walk"),
        (58, 59, 3, "walk"),
        (58, 60, 1, "walk"),
        (65, 66, 10, "boat"),
    ]:
        # Replace generic cluster links where the scene relationship is more specific.
        aa, bb = f"place_e{a:02}", f"place_e{b:02}"
        edges[:] = [e for e in edges if bb not in (e["from"], e["to"])]
        link(aa, bb, minutes, mode)
        # Arrive through the front zone, never directly into backstage or summit.

    # Containers describe a shared venue without creating teleport destinations.
    for venue, name, ids in [
        ("girlsaward", "GirlsAward Venue", [14, 15]),
        ("takao_park", "Mount Takao Trail and Summit", [19, 20]),
        ("yomiuriland_park", "Yomiuriland Park", [24, 25]),
        ("snow_resort", "Unverified Snow Resort", [26, 27]),
        ("muscats_venue", "Ebisu Muscats Performance Venue", [42, 43]),
        ("tsukiji_market", "Tsukiji Outer Market", [44, 45]),
        ("cup_noodles_museum", "Cup Noodles Museum Yokohama", [48, 49]),
        ("hayato_restaurant", "Hayato's Restaurant Workplace", [50, 51]),
        ("ballet_competition", "Ballet Competition Venue", [52, 53]),
        ("nagatoro_camp", "Nagatoro Campground", [58, 59, 60]),
    ]:
        parent = locations[f"place_e{ids[0]:02}"]["area_id"]
        areas.append(
            {
                "id": venue,
                "name": name,
                "parent_id": parent,
                "note": "Venue container; visit its individual scene areas.",
            }
        )
        for number in ids:
            locations[f"place_e{number:02}"]["area_id"] = venue

    result = {
        "world_id": "six_strangers",
        "version": 3,
        "time": {"start_minute": 0, "minute_label": "minutes_since_start"},
        "defaults": {
            "probabilities": {
                "p_exit_A": 0.2,
                "p_pass_C": 0.5,
                "p_event_at_C": 0.25,
                "p_enter_B": 0.2,
                "p_describe_B": 0.6,
            }
        },
        "map": {
            "title": "Six Strangers · Tokyo & beyond",
            "coordinate_system": "relative_km",
            "origin_label": "the house",
            "nearby_radius_km": 16,
            "route_policy": "shortest_time",
            "areas": areas,
            "sources": [
                "documentation/research/terrace_house_bgitc_places.md",
                "documentation/research/terrace_house_regional_reference.png",
            ],
            "notes": [
                "Regional offsets follow the supplied approximate straight-line distance table, not private addresses.",
                "East is +x; north is +y; origin is the house. Indoor positions use a separate 0–100 functional layout.",
                "All route minutes are gameplay estimates, not researched journey times; the engine adds its departure cost.",
                "The house is scene-derived, not a verified floor plan. The local cafe is a game addition.",
                "Unverified venues have no regional coordinates; named historical venues are not claims of current operation.",
                "O13 aliases H15. Other unnamed scene types remain placeholders pending direct episode review.",
            ],
        },
        "locations": locations,
        "edges": edges,
    }
    TARGET.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {len(locations)} atomic locations, {len(areas)} areas, {len(edges)} directed routes"
    )


if __name__ == "__main__":
    build()
