"""The Intention record (kept apart from agenda.py so the world model can persist it)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Intention:
    kind: str            # pursue | compete_for | test_loyalty
    target: str
    priority: float
    reason: str
    expires_day: int

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Intention":
        return cls(str(raw["kind"]), str(raw["target"]), float(raw.get("priority") or 0),
                   str(raw.get("reason") or ""), int(raw.get("expires_day") or 0))
