# backend/app/engine/world/graph.py
from typing import Dict, List
from .location import Location
from .edge import PathEdge


class WorldGraph:
    def __init__(self):
        self.locations: Dict[str, Location] = {}
        self.edges_from: Dict[str, List[PathEdge]] = {}

    def add_location(self, location: Location) -> None:
        if location.id in self.locations:
            raise ValueError(f"Duplicate location id: {location.id}")
        self.locations[location.id] = location
        self.edges_from.setdefault(location.id, [])

    def add_edge(self, edge: PathEdge) -> None:
        if edge.from_id not in self.locations:
            raise KeyError(f"Unknown location: {edge.from_id}")
        if edge.to_id not in self.locations:
            raise KeyError(f"Unknown location: {edge.to_id}")
        self.edges_from[edge.from_id].append(edge)

    def get_neighbors(self, location_id: str) -> List[PathEdge]:
        return self.edges_from.get(location_id, [])

    def get_location(self, location_id: str) -> Location:
        return self.locations[location_id]
