"""One person: body state, mind, routine. Location is never stored here —
`get_location()` reads the world index so there is no second copy to drift."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from backend.app.engine.world_model.routine import AVAILABILITY, Routine
from backend.app.engine.world_model.world import World


@dataclass
class CharacterState:
    id: str
    name: str
    availability: str = "awake"
    activity: str = ""
    mood: str = ""
    aim: str = ""
    routine: Routine = field(default_factory=Routine)
    spoke_turns: list[int] = field(default_factory=list)   # most recent last, capped
    last_contact_day: int = -1
    descriptor: str = ""            # how strangers refer to them ("the hair stylist")
    slot_group: str = ""            # men | women | ... when a cast lifecycle defines one
    block: str = ""                 # key of the routine block currently driving them ("" = free time)

    def __post_init__(self) -> None:
        if self.availability not in AVAILABILITY:
            raise ValueError(f"unknown availability {self.availability!r}")

    def get_location(self, world: World) -> Optional[str]:
        return world.where_is(self.id)

    @property
    def can_hear(self) -> bool:
        return self.availability in ("awake", "busy")

    def record_spoke(self, turn: int) -> None:
        self.spoke_turns = (self.spoke_turns + [turn])[-6:]

    def turns_since_spoke(self, turn: int) -> int:
        return turn - self.spoke_turns[-1] if self.spoke_turns else 99

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "availability": self.availability, "activity": self.activity,
                "mood": self.mood, "aim": self.aim, "routine": self.routine.to_dict(),
                "spoke_turns": list(self.spoke_turns), "last_contact_day": self.last_contact_day,
                "descriptor": self.descriptor, "slot_group": self.slot_group, "block": self.block}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterState":
        return cls(id=str(data["id"]), name=str(data.get("name") or data["id"]),
                   availability=str(data.get("availability") or "awake"), activity=str(data.get("activity") or ""),
                   mood=str(data.get("mood") or ""), aim=str(data.get("aim") or ""),
                   routine=Routine.from_dict(data.get("routine") or {}),
                   spoke_turns=[int(t) for t in data.get("spoke_turns") or []],
                   last_contact_day=int(data.get("last_contact_day", -1)),
                   descriptor=str(data.get("descriptor") or ""), slot_group=str(data.get("slot_group") or ""),
                   block=str(data.get("block") or ""))
