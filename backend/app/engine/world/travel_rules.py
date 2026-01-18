from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .edge import PathEdge
from .graph import EdgeList, WorldGraph
from .ids import LocationId


@dataclass(frozen=True)
class TravelSegment:
    """One hop in a route (edge-based)."""

    edge: PathEdge


@dataclass(frozen=True)
class TravelRoute:
    """A resolved route from A to B."""

    from_id: LocationId
    to_id: LocationId
    segments: Tuple[TravelSegment, ...]

    def intermediate_id(self):
        # Returns LocationId or None (allowed simple type)
        if len(self.segments) == 2:
            return self.segments[0].edge.to_id
        return None

    def total_transit_minutes(self) -> int:
        return sum(seg.edge.minutes for seg in self.segments)


class TravelRules:
    """Rule-driven, seeded route selection.

    This encodes the agreed behavior:
    - The system (not user, not AI) chooses the path.
    - Forks are resolved via seeded randomness + (future) flags.
    - For MVP we allow either:
        * direct travel (A->B)
        * one intermediate travel (A->C->B)
    """

    def __init__(self, seed: int):
        import random

        self._rng = random.Random(seed)


    def choose_edge(self, edges):
        """Choose an unblocked edge deterministically.

        - Filters blocked edges
        - Uses the instance's seeded RNG (self._rng) for stable selection
        - Raises RuntimeError if no edges are available
        """
        candidates = [e for e in edges if not getattr(e, "blocked", False)]
        if not candidates:
            raise RuntimeError("No available (unblocked) travel edges")
        return self._rng.choice(candidates)


    def resolve_route(self, graph: WorldGraph, from_id: LocationId, to_id: LocationId) -> TravelRoute:
        direct: EdgeList = graph.get_direct_edges(from_id, to_id)
        direct_edges = tuple(e for e in direct.to_tuple() if not e.blocked)
        if direct_edges:
            chosen = self._rng.choice(direct_edges)
            return TravelRoute(from_id=from_id, to_id=to_id, segments=(TravelSegment(edge=chosen),))

        # Try one-intermediate routes: A->X and X->B.
        outgoing = tuple(e for e in graph.get_outgoing(from_id).to_tuple() if not e.blocked)

        candidates: Tuple[Tuple[PathEdge, PathEdge], ...] = tuple(
            (e1, e2)
            for e1 in outgoing
            for e2 in graph.get_direct_edges(e1.to_id, to_id).to_tuple()
            if not e2.blocked
        )

        if not candidates:
            raise RuntimeError(f"No valid route from {from_id} to {to_id}")

        chosen_pair = self._rng.choice(candidates)
        return TravelRoute(
            from_id=from_id,
            to_id=to_id,
            segments=(TravelSegment(edge=chosen_pair[0]), TravelSegment(edge=chosen_pair[1])),
        )