from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .ids import LocationId


@dataclass(frozen=True)
class PathEdge:
    """Directed edge between two locations.

    Compatibility: unit tests and some callers may pass ids as raw strings; we
    coerce them to LocationId.
    """

    from_id: Union[LocationId, str]
    to_id: Union[LocationId, str]
    minutes: int

    is_transit: bool = False
    blocked: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.from_id, str):
            object.__setattr__(self, "from_id", LocationId(self.from_id))
        if isinstance(self.to_id, str):
            object.__setattr__(self, "to_id", LocationId(self.to_id))

        if not isinstance(self.minutes, int):
            raise TypeError("PathEdge.minutes must be int")
        if self.minutes <= 0:
            raise ValueError("PathEdge.minutes must be positive")
