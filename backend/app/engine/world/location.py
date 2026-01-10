from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Tuple, Union

from .ids import LocationId


@dataclass(frozen=True)
class Location:
    """An atomic place in the world (no nesting).

    Sub-places (rooms) are represented as separate Location nodes.

    Compatibility: unit tests and some callers may pass `id` as a raw str and
    `tags` as a list; we coerce those to the canonical types.
    """

    id: Union[LocationId, str]
    name: str
    description: str
    tags: Union[Tuple[str, ...], Iterable[str]] = field(default_factory=tuple)

    allows_phone: bool = True
    is_transit: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.id, str):
            object.__setattr__(self, "id", LocationId(self.id))

        # Coerce tags to an immutable tuple for hashing/consistency.
        if not isinstance(self.tags, tuple):
            object.__setattr__(self, "tags", tuple(self.tags))

        if not self.name.strip():
            raise ValueError("Location.name must be non-empty")
