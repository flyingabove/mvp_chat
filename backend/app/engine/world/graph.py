from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .edge import PathEdge
from .ids import LocationId
from .location import Location


@dataclass(frozen=True)
class EdgeList:
    """Immutable container for edges."""

    edges: Tuple[PathEdge, ...]

    def to_tuple(self) -> Tuple[PathEdge, ...]:
        return self.edges


class WorldGraph:
    """Authoritative topological world graph."""

    def __init__(self) -> None:
        self._locations: Dict[str, Location] = {}
        self._outgoing: Dict[str, Tuple[PathEdge, ...]] = {}

    @property
    def locations(self) -> Dict[str, Location]:
        """Public read-only view of locations keyed by location id string."""
        return self._locations

    def add_location(self, location: Location) -> None:
        key = location.id.value
        if key in self._locations:
            raise ValueError(f"Duplicate location id: {location.id}")
        self._locations[key] = location
        self._outgoing.setdefault(key, tuple())

    def add_edge(self, edge: PathEdge) -> None:
        if edge.from_id.value not in self._locations:
            raise KeyError(f"Unknown from_id: {edge.from_id}")
        if edge.to_id.value not in self._locations:
            raise KeyError(f"Unknown to_id: {edge.to_id}")

        key = edge.from_id.value
        self._outgoing[key] = self._outgoing.get(key, tuple()) + (edge,)

    def get_location(self, location_id: LocationId) -> Location:
        return self._locations[location_id.value]

    def get_outgoing(self, from_id: LocationId) -> EdgeList:
        return EdgeList(edges=self._outgoing.get(from_id.value, tuple()))

    def get_neighbors(self, from_id: str | LocationId) -> Tuple[PathEdge, ...]:
        """Compatibility helper for tests: return outgoing edges from a node."""
        lid = from_id if isinstance(from_id, LocationId) else LocationId(from_id)
        if lid.value not in self._locations:
            raise KeyError(f"Unknown location id: {lid}")
        return self._outgoing.get(lid.value, tuple())

    def get_direct_edges(self, from_id: LocationId, to_id: LocationId) -> EdgeList:
        edges = tuple(e for e in self._outgoing.get(from_id.value, tuple()) if e.to_id == to_id)
        return EdgeList(edges=edges)
