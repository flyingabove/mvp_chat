"""Story-independent atlas metadata; geography never substitutes for travel edges."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import hypot, isfinite


@dataclass(frozen=True)
class MapPoint:
    x: float
    y: float

    def __post_init__(self):
        if not all(isfinite(v) for v in (self.x, self.y)):
            raise ValueError("Map coordinates must be finite")


@dataclass(frozen=True)
class PlaceResearch:
    source_ids: tuple[str, ...] = ()
    status: str = "game_added"
    episodes: str = ""
    note: str = ""

    def __post_init__(self):
        object.__setattr__(self, "source_ids", tuple(self.source_ids))
        if self.status not in {
            "named",
            "approximate",
            "unverified",
            "scene_derived",
            "game_added",
        }:
            raise ValueError(f"Unknown research status: {self.status}")


@dataclass(frozen=True)
class MapArea:
    """Non-visitable grouping; optional offsets are schematic km east/north."""

    id: str
    name: str
    parent_id: str | None = None
    position: MapPoint | None = None
    distance_min_km: float | None = None
    distance_max_km: float | None = None
    direction: str = ""
    note: str = ""

    def __post_init__(self):
        low, high = self.distance_min_km, self.distance_max_km
        if (low is None) != (high is None):
            raise ValueError("Distance bounds must be supplied together")
        if low is not None:
            if not (isfinite(low) and isfinite(high) and 0 <= low <= high):
                raise ValueError("Invalid distance range")
            if (
                self.position
                and not low - 0.01
                <= hypot(self.position.x, self.position.y)
                <= high + 0.01
            ):
                raise ValueError(
                    f"Area {self.id} lies outside its research distance range"
                )


@dataclass(frozen=True)
class WorldMap:
    title: str = "World map"
    origin_label: str = "origin"
    nearby_radius_km: float = 16
    coordinate_system: str = "relative_km"
    notes: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    areas: tuple[MapArea, ...] = ()
    route_policy: str = "legacy"

    @classmethod
    def from_dict(cls, data: dict | None) -> WorldMap:
        data = data or {}
        areas = []
        for item in data.get("areas", []):
            obj = dict(item)
            if obj.get("position") is not None:
                obj["position"] = MapPoint(**obj["position"])
            areas.append(MapArea(**obj))
        result = cls(
            title=data.get("title", "World map"),
            origin_label=data.get("origin_label", "origin"),
            nearby_radius_km=float(data.get("nearby_radius_km", 16)),
            coordinate_system=data.get("coordinate_system", "relative_km"),
            notes=tuple(data.get("notes", [])),
            sources=tuple(data.get("sources", [])),
            areas=tuple(areas),
            route_policy=data.get("route_policy", "legacy"),
        )
        result.validate()
        return result

    def validate(self):
        areas = {area.id: area for area in self.areas}
        if len(areas) != len(self.areas):
            raise ValueError("Duplicate map area")
        if self.coordinate_system != "relative_km":
            raise ValueError("Unsupported map coordinate system")
        if not isfinite(self.nearby_radius_km) or self.nearby_radius_km <= 0:
            raise ValueError("Nearby radius must be finite and positive")
        if self.route_policy not in {"legacy", "shortest_time"}:
            raise ValueError("Unsupported route policy")
        for area in self.areas:
            seen = {area.id}
            parent = area.parent_id
            while parent:
                if parent not in areas or parent in seen:
                    raise ValueError("Unknown or cyclic map area parent")
                seen.add(parent)
                parent = areas[parent].parent_id

    def validate_locations(self, locations):
        area_ids = {area.id for area in self.areas}
        for loc in locations.values():
            if loc.area_id is not None and loc.area_id not in area_ids:
                raise ValueError(f"Unknown area for location {loc.id}: {loc.area_id}")
            if loc.map_position and (
                loc.area_id is None
                or not all(
                    0 <= v <= 100 for v in (loc.map_position.x, loc.map_position.y)
                )
            ):
                raise ValueError(
                    "Interior positions require an area and coordinates in 0–100"
                )

    def to_dict(self):
        return asdict(self)


def location_map_fields(data: dict) -> dict:
    """Shared parser used by both world loaders, with legacy-safe defaults."""
    return {
        "area_id": data.get("area_id"),
        "map_position": MapPoint(**data["map_position"])
        if data.get("map_position")
        else None,
        "research": PlaceResearch(**data.get("research", {})),
    }


def world_map_payload(graph) -> dict:
    """One API representation for story metadata and in-session map requests."""
    return {
        **graph.world_map.to_dict(),
        "locations": [
            {
                "id": lid,
                "name": loc.name,
                "description": loc.description,
                "area_id": loc.area_id,
                "map_position": asdict(loc.map_position) if loc.map_position else None,
                "research": asdict(loc.research),
            }
            for lid, loc in graph.locations.items()
        ],
        "routes": [
            {
                "from": edge.from_id.value,
                "to": edge.to_id.value,
                "minutes": edge.minutes,
                "mode": edge.mode,
                "estimated": edge.estimated,
                "blocked": edge.blocked,
            }
            for lid in graph.locations
            for edge in graph.get_neighbors(lid)
        ],
    }
