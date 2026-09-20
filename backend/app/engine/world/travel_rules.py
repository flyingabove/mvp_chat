from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple
from collections import deque
import logging

from .edge import PathEdge
from .graph import EdgeList, WorldGraph
from .ids import LocationId

logger = logging.getLogger(__name__)


class TravelBlockedError(RuntimeError):
    """Raised when the only path(s) between two locations are blocked.

    A09 fix: this must be distinguished from a genuinely disconnected graph
    (an authoring bug / "island"). A blocked edge is a deliberate runtime
    constraint (a locked door, a private room) and must reject travel, not
    silently reroute through a fabricated fallback edge that ignores the
    block.
    """


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
        """Resolve route using: direct -> one-intermediate -> multi-hop BFS -> error."""
        
        # 1. Try direct route
        direct: EdgeList = graph.get_direct_edges(from_id, to_id)
        direct_edges = tuple(e for e in direct.to_tuple() if not e.blocked)
        if direct_edges:
            chosen = self._rng.choice(direct_edges)
            return TravelRoute(from_id=from_id, to_id=to_id, segments=(TravelSegment(edge=chosen),))

        # 2. Try one-intermediate routes: A->X and X->B.
        outgoing = tuple(e for e in graph.get_outgoing(from_id).to_tuple() if not e.blocked)
        candidates: Tuple[Tuple[PathEdge, PathEdge], ...] = tuple(
            (e1, e2)
            for e1 in outgoing
            for e2 in graph.get_direct_edges(e1.to_id, to_id).to_tuple()
            if not e2.blocked
        )
        if candidates:
            chosen_pair = self._rng.choice(candidates)
            return TravelRoute(
                from_id=from_id,
                to_id=to_id,
                segments=(TravelSegment(edge=chosen_pair[0]), TravelSegment(edge=chosen_pair[1])),
            )

        # 3. Try multi-hop BFS pathfinding (A->X->Y->...->B), unblocked edges only
        path = self._find_path_bfs(graph, from_id, to_id, ignore_blocked=False)
        if path:
            segments = tuple(TravelSegment(edge=edge) for edge in path)
            return TravelRoute(from_id=from_id, to_id=to_id, segments=segments)

        # 4. No *unblocked* path found. Before treating this as a structural
        # island, check whether a path exists at all if we ignore the
        # `blocked` flag. If one does, the destination is reachable in the
        # authored graph but currently locked/blocked — that is a
        # deliberate runtime constraint (A09) and travel must be rejected,
        # never silently rerouted through a fabricated edge that bypasses
        # the block.
        if self._find_path_bfs(graph, from_id, to_id, ignore_blocked=True) is not None:
            raise TravelBlockedError(
                f"No unblocked route from {from_id} to {to_id}: the only path(s) are blocked"
            )

        # 5. Truly disconnected (authoring bug) - ISLAND DETECTED!
        self._log_island_error(from_id, to_id, graph)

        # 6. CREATE FALLBACK DYNAMIC EDGE (in-memory only). This only ever
        # fires for a genuine authoring-time island, never for a blocked
        # edge (handled above).
        dynamic_edge = self._create_dynamic_edge(from_id, to_id)
        self._inject_dynamic_edge(graph, dynamic_edge)
        logger.warning(f"Created temporary dynamic edge: {from_id} -> {to_id} ({dynamic_edge.minutes} min)")

        return TravelRoute(from_id=from_id, to_id=to_id, segments=(TravelSegment(edge=dynamic_edge),))

    def _find_path_bfs(
        self,
        graph: WorldGraph,
        from_id: LocationId,
        to_id: LocationId,
        *,
        ignore_blocked: bool = False,
    ) -> Tuple[PathEdge, ...] | None:
        """BFS to find multi-hop path from from_id to to_id.

        When ignore_blocked=True, blocked edges are traversable — used only
        to distinguish "reachable but blocked" (A09: must reject) from
        "genuinely disconnected" (island: falls back to a dynamic edge).

        Returns tuple of edges forming the path, or None if no path exists.
        """
        if from_id == to_id:
            return tuple()

        queue = deque([(from_id, tuple())])  # (current_id, edges_taken)
        visited = {from_id}
        max_hops = 10  # Prevent infinite loops

        while queue:
            current_id, path_edges = queue.popleft()

            # Limit path length
            if len(path_edges) >= max_hops:
                continue

            # Explore neighbors
            for edge in graph.get_outgoing(current_id).to_tuple():
                if not ignore_blocked and getattr(edge, "blocked", False):
                    continue

                next_id = edge.to_id
                if next_id == to_id:
                    # Found path!
                    return path_edges + (edge,)

                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, path_edges + (edge,)))

        return None

    def _log_island_error(self, from_id: LocationId, to_id: LocationId, graph: WorldGraph) -> None:
        """Log GIANT error message when island is detected."""
        from_name = graph.get_location(from_id).name
        to_name = graph.get_location(to_id).name

        error_msg = f"""
╔════════════════════════════════════════════════════════════════════════════╗
║                    🚨 WORLD GRAPH ISLAND DETECTED 🚨                       ║
╚════════════════════════════════════════════════════════════════════════════╝

CRITICAL: No path exists between two locations in world graph!

FROM: {from_id} ({from_name})
TO:   {to_id} ({to_name})

PATHFINDING ATTEMPTS:
  ✗ Direct edge (A->B)
  ✗ One-intermediate (A->C->B)  
  ✗ Multi-hop BFS (A->C->D->...->B)

ROOT CAUSE: World JSON has disconnected location groups (islands).

LOCATIONS IN GRAPH:
  Total: {len(graph.locations)}
  {', '.join(f'{loc_id}' for loc_id in sorted(graph.locations.keys()))}

ACTION REQUIRED:
  1. Review the story's world JSON file
  2. Verify all locations are reachable from start_location
  3. Add missing edges to connect islands
  4. Redeploy

WORKAROUND (current session only):
  - A temporary dynamic edge will be created for this route
  - Edge is in-memory only and will NOT persist
  - This should NOT happen in production!

═══════════════════════════════════════════════════════════════════════════════
"""
        logger.error(error_msg)

    def _create_dynamic_edge(self, from_id: LocationId, to_id: LocationId) -> PathEdge:
        """Create a temporary in-memory edge with random travel time.
        
        Returns PathEdge with:
        - Random travel time (8-25 minutes)
        - Not blocked
        - Marked as transit for island bridging
        """
        travel_minutes = self._rng.randint(8, 25)
        return PathEdge(
            from_id=from_id,
            to_id=to_id,
            minutes=travel_minutes,
            blocked=False,
            is_transit=True  # Mark as special transit route
        )

    def _inject_dynamic_edge(self, graph: WorldGraph, edge: PathEdge) -> None:
        """Inject edge directly into graph's internal structure (in-memory only).
        
        Does NOT call add_edge() because we want to bypass validation.
        Edge will exist for this session only and won't be saved to JSON.
        """
        key = edge.from_id.value
        graph._outgoing[key] = graph._outgoing.get(key, tuple()) + (edge,)

