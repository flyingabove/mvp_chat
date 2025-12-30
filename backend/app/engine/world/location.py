from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from .ids import LocationId


@dataclass(frozen=True)
class Location:
    """An atomic place in the world (no nesting).

    Sub-places (rooms) are represented as separate Location nodes.
    """

    id: LocationId
    name: str
    description: str
    tags: Tuple[str, ...] = field(default_factory=tuple)

    allows_phone: bool = True
    is_transit: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Location.name must be non-empty")
