from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .edge import PathEdge
from .exposure import ExposureConfig
from .graph import WorldGraph
from .ids import LocationId
from .location import Location
from .travel_resolver import TravelTiming


@dataclass(frozen=True)
class WorldDefinition:
    world_id: str
    version: int
    start_minute: int
    graph: WorldGraph
    exposure_config: ExposureConfig
    travel_timing: TravelTiming


class WorldDefinitionLoader:
    """Loads a WorldDefinition from a JSON string or a parsed dict.

    The input format matches the authoring JSON you defined for creators/AI.
    This loader returns only classes (no dict/list at API boundaries).
    """

    def from_json_str(self, json_text: str) -> WorldDefinition:
        import json

        data = json.loads(json_text)
        return self.from_dict(data)

    def from_dict(self, data: Dict[str, Any]) -> WorldDefinition:
        world_id = str(data.get("world_id", "")).strip()
        if not world_id:
            raise ValueError("world_id is required")

        version = int(data.get("version", 1))
        start_minute = int(data.get("time", {}).get("start_minute", 0))

        probs = data.get("defaults", {}).get("probabilities", {})
        exposure_config = ExposureConfig(
            p_exit_A=float(probs.get("p_exit_A", 0.0)),
            p_pass_C=float(probs.get("p_pass_C", 0.0)),
            p_event_at_C=float(probs.get("p_event_at_C", 0.0)),
            p_enter_B=float(probs.get("p_enter_B", 0.0)),
            p_describe_B=float(probs.get("p_describe_B", 0.0)),
        )
        exposure_config.validate()

        # Travel timing: keep minimal for MVP. (exit cost only)
        timing = TravelTiming(exit_minutes=int(data.get("defaults", {}).get("exit_minutes", 1)))
        timing.validate()

        graph = WorldGraph()

        # Locations
        locations = data.get("locations", {})
        for lid, loc in locations.items():
            loc_id = LocationId(str(lid))
            name = str(loc.get("name", "")).strip()
            desc = str(loc.get("description", ""))
            tags = tuple(str(t) for t in (loc.get("tags") or []))
            allows_phone = bool(loc.get("allows_phone", True))
            is_transit = bool(loc.get("is_transit", False))

            graph.add_location(
                Location(
                    id=loc_id,
                    name=name,
                    description=desc,
                    tags=tags,
                    allows_phone=allows_phone,
                    is_transit=is_transit,
                )
            )

        # Edges
        for e in data.get("edges", []) or []:
            from_id = LocationId(str(e["from"]))
            to_id = LocationId(str(e["to"]))
            minutes = int(e["minutes"])
            is_transit = bool(e.get("is_transit", False))
            blocked = bool(e.get("blocked", False))
            graph.add_edge(PathEdge(from_id=from_id, to_id=to_id, minutes=minutes, is_transit=is_transit, blocked=blocked))

        return WorldDefinition(
            world_id=world_id,
            version=version,
            start_minute=start_minute,
            graph=graph,
            exposure_config=exposure_config,
            travel_timing=timing,
        )
