"""A person's directional feelings toward others, read through the character graph.

A Bond wraps the graph's existing RelationshipEdge: `feelings` is the very
same RelationshipState object, so there is exactly one stored copy of how
anyone feels about anyone.
"""
from __future__ import annotations

from typing import Any, Optional

FEELING_DIMENSIONS = ("trust", "affection", "suspicion", "fear", "jealousy")


class Bond:
    def __init__(self, owner: str, target: str, edge: Any) -> None:
        self.owner = owner
        self.target = target
        self._edge = edge

    @property
    def feelings(self) -> Any:
        return self._edge.state

    def as_dict(self) -> dict[str, float]:
        return {dim: float(getattr(self.feelings, dim, 0.0) or 0.0) for dim in FEELING_DIMENSIONS}

    def warmth(self) -> float:
        return (self.feelings.trust + self.feelings.affection) / 2


class Heart:
    def __init__(self, owner: str, graph: Any) -> None:
        self.owner = owner
        self._graph = graph

    def bond(self, target: str) -> Optional[Bond]:
        edge = self._graph.get_edge(self.owner, target) if self._graph is not None else None
        return Bond(self.owner, target, edge) if edge is not None else None

    def bonds(self) -> list[Bond]:
        if self._graph is None:
            return []
        return [Bond(self.owner, edge.to_id, edge) for edge in self._graph.get_edges_from(self.owner)]
