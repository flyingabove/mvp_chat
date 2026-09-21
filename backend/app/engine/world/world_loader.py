# backend/app/engine/world/world_loader.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .clock import WorldClock
from .edge import PathEdge
from .exposure import ExposureResolver
from .graph import WorldGraph
from .location import Location
from .map_model import WorldMap, location_map_fields
from .travel_resolver import TravelResolver
from .travel_rules import TravelRules
from backend.app.utils.id_utils import build_deterministic_uuid
from backend.app.config.settings import DEFAULT_USER_ID, DEFAULT_INSTANCE


@dataclass(frozen=True)
class WorldLoadResult:
    world_graph: WorldGraph
    world_clock: WorldClock
    travel_resolver: TravelResolver
    seed: int
    probabilities: dict


class WorldLoader:
    """Loads a flat World JSON into runtime classes."""

    @classmethod
    def load_from_file(
        cls,
        filepath: str,
        *,
        seed: int = 0,
        user_id: str = DEFAULT_USER_ID,
        story_id: str = "unknown_story",
        instance: int = DEFAULT_INSTANCE,
    ) -> WorldLoadResult:
        p = Path(filepath)
        data = json.loads(p.read_text(encoding="utf-8"))

        graph = WorldGraph(WorldMap.from_dict(data.get("map")))

        locs = data.get("locations") or {}
        for loc_id, obj in locs.items():
            loc_uuid = str(obj.get("uuid", "")) or build_deterministic_uuid(
                user_id=user_id,
                story_id=story_id,
                instance=instance,
                entity_id=loc_id,
            )

            graph.add_location(
                Location(
                    id=loc_id,
                    name=str(obj.get("name", loc_id)),
                    description=str(obj.get("description", "")),
                    tags=list(obj.get("tags", [])),
                    allows_phone=bool(obj.get("allows_phone", True)),
                    is_transit=bool(obj.get("is_transit", False)),
                    uuid=loc_uuid,
                    **location_map_fields(obj),
                )
            )

        graph.world_map.validate_locations(graph.locations)
        for e in data.get("edges") or []:
            graph.add_edge(
                PathEdge(
                    from_id=str(e.get("from")),
                    to_id=str(e.get("to")),
                    minutes=int(e.get("minutes", 1)),
                    is_transit=bool(e.get("is_transit", False)),
                    blocked=bool(e.get("blocked", False)),
                    mode=str(e.get("mode", "walk")),
                    estimated=bool(e.get("estimated", True)),
                )
            )

        start_minute = int((data.get("time") or {}).get("start_minute", 0))
        clock = WorldClock(start_minute=start_minute)

        probs = ((data.get("defaults") or {}).get("probabilities") or {})
        # Stable defaults if missing
        probabilities = {
            "p_exit_A": float(probs.get("p_exit_A", 0.2)),
            "p_pass_C": float(probs.get("p_pass_C", 0.5)),
            "p_event_at_C": float(probs.get("p_event_at_C", 0.25)),
            "p_enter_B": float(probs.get("p_enter_B", 0.2)),
            "p_describe_B": float(probs.get("p_describe_B", 0.6)),
        }

        rules = TravelRules(seed=seed)
        exposure = ExposureResolver(seed=seed, probs=probabilities)
        resolver = TravelResolver(graph=graph, clock=clock, rules=rules, exposure_resolver=exposure)

        return WorldLoadResult(
            world_graph=graph,
            world_clock=clock,
            travel_resolver=resolver,
            seed=seed,
            probabilities=probabilities,
        )

    @classmethod
    def try_load_story_world(
        cls,
        story_id: str,
        stories_dir: str,
        *,
        seed: int = 0,
        user_id: str = DEFAULT_USER_ID,
        instance: int = DEFAULT_INSTANCE,
    ) -> Optional[WorldLoadResult]:
        """Convenience: load backend/app/stories/<story_id>_world.json or backend/app/stories/<subdir>/<story_id>_world.json if present."""
        p = Path(stories_dir) / f"{story_id}_world.json"
        if not p.exists():
            # Try subdirectories
            stories_path = Path(stories_dir)
            if stories_path.exists():
                for subdir in stories_path.iterdir():
                    if subdir.is_dir() and not subdir.name.startswith("__"):
                        alt_path = subdir / f"{story_id}_world.json"
                        if alt_path.exists():
                            return cls.load_from_file(
                                str(alt_path),
                                seed=seed,
                                user_id=user_id,
                                story_id=story_id,
                                instance=instance,
                            )
            return None
        return cls.load_from_file(
            str(p),
            seed=seed,
            user_id=user_id,
            story_id=story_id,
            instance=instance,
        )
