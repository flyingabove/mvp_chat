"""World truth: what actually happened. Immutable once committed; lies and
mistakes live in memories, never here."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    id: str
    minute: int
    place: str
    participants: tuple[str, ...]
    truth: str
    kind: str = "scene"                 # scene | offscreen | milestone | authored | inspection
    visibility: str = "private"         # private (participants only) | public (a visible trace exists)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "minute": self.minute, "place": self.place,
                "participants": list(self.participants), "truth": self.truth,
                "kind": self.kind, "visibility": self.visibility}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(id=str(data["id"]), minute=int(data.get("minute") or 0), place=str(data.get("place") or ""),
                   participants=tuple(data.get("participants") or ()), truth=str(data.get("truth") or ""),
                   kind=str(data.get("kind") or "scene"), visibility=str(data.get("visibility") or "private"))
