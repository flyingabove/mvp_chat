"""Anything that can be somewhere: characters, the player, objects, evidence."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ENTITY_KINDS = ("character", "player", "object", "evidence")


@dataclass
class Entity:
    id: str
    kind: str = "object"
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    props: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in ENTITY_KINDS:
            raise ValueError(f"unknown entity kind {self.kind!r}")
        if not self.name:
            self.name = self.id.replace("_", " ")

    def matches(self, text: str) -> bool:
        """True when `text` names this entity or an alias as whole words (case-insensitive)."""
        return any(re.search(rf"\b{re.escape(term)}\b", text or "", re.I)
                   for term in [self.name, *self.aliases] if term)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "name": self.name,
                "aliases": list(self.aliases), "props": dict(self.props)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entity":
        return cls(id=str(data["id"]), kind=str(data.get("kind") or "object"),
                   name=str(data.get("name") or ""), aliases=list(data.get("aliases") or []),
                   props=dict(data.get("props") or {}))
