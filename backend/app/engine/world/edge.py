from __future__ import annotations

from dataclasses import dataclass

from .ids import LocationId


@dataclass(frozen=True)
class PathEdge:
    """Directed edge between two locations."""

    from_id: LocationId
    to_id: LocationId
    minutes: int

    is_transit: bool = False
    blocked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.minutes, int):
            raise TypeError("PathEdge.minutes must be int")
        if self.minutes <= 0:
            raise ValueError("PathEdge.minutes must be positive")