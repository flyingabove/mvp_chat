"""Routine envelopes: where a character wants to be, doing what, at a given minute.

Blocks may wrap midnight (23:30-07:00). Block edges jitter by a seeded amount per
character per day, so the world is not metronomic but replays agree.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.app.engine.world_model.world import MINUTES_PER_DAY, World, parse_hhmm

AVAILABILITY = ("awake", "busy", "out", "asleep")


@dataclass(frozen=True)
class RoutineBlock:
    start: str
    end: str
    place: str
    activity: str
    availability: str = "busy"
    days: Optional[tuple[int, ...]] = None      # weekday numbers, 0 = Monday; None = every day
    variance: int = 0                            # +/- minutes of seeded jitter on both edges
    hard: bool = False                           # overrides the anti-vanish rule (sleep, fixed appointment)

    def __post_init__(self) -> None:
        if self.availability not in AVAILABILITY:
            raise ValueError(f"unknown availability {self.availability!r}")
        parse_hhmm(self.start), parse_hhmm(self.end)

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "place": self.place, "activity": self.activity,
                "availability": self.availability, "days": list(self.days) if self.days is not None else None,
                "variance": self.variance, "hard": self.hard}

    @classmethod
    def from_dict(cls, data: dict[str, Any], home: str = "") -> "RoutineBlock":
        place = str(data.get("place") or "home")
        return cls(start=str(data["start"]), end=str(data["end"]),
                   place=home if place == "home" and home else place,
                   activity=str(data.get("activity") or ""), availability=str(data.get("availability") or "busy"),
                   days=tuple(data["days"]) if data.get("days") is not None else None,
                   variance=int(data.get("variance") or 0), hard=bool(data.get("hard")))


def block_key(block: Optional[RoutineBlock]) -> str:
    """Stable identity of a block ("" = free time); also encodes its place."""
    return f"{block.start}-{block.end}@{block.place}:{block.activity}" if block else ""


def default_blocks(home: str) -> list[RoutineBlock]:
    """Everyone sleeps; stories add the rest."""
    return [RoutineBlock("23:30", "07:00", home, "sleeping", "asleep", variance=30, hard=True)]


@dataclass
class Routine:
    blocks: list[RoutineBlock] = field(default_factory=list)
    home: str = ""
    free_place: str = ""        # where they go when a block away from home ends ("" = home)

    def active(self, world: World, minute: int, character_id: str, seed: str) -> Optional[RoutineBlock]:
        """The block covering `minute`, after seeded jitter; None = free time."""
        for block in self.blocks:
            if self._covers(block, world, minute, character_id, seed):
                return block
        return None

    @staticmethod
    def _jitter(block: RoutineBlock, day: int, character_id: str, seed: str) -> tuple[int, int]:
        if not block.variance:
            return 0, 0
        rng = random.Random(f"{seed}:routine:{character_id}:{day}:{block.start}")
        return rng.randint(-block.variance, block.variance), rng.randint(-block.variance, block.variance)

    def _covers(self, block: RoutineBlock, world: World, minute: int, character_id: str, seed: str) -> bool:
        day = world.day_index(minute)
        # A block that wraps midnight may have started the previous calendar day.
        for start_day in (day, day - 1):
            start = world.absolute_minute(start_day, block.start)
            end = world.absolute_minute(start_day, block.end)
            if end <= start:
                end += MINUTES_PER_DAY
            if block.days is not None and world.weekday(start) not in block.days:
                continue
            j_start, j_end = self._jitter(block, start_day, character_id, seed)
            if start + j_start <= minute < end + j_end:
                return True
        return False

    def boundaries(self, world: World, start: int, end: int, character_id: str, seed: str) -> list[int]:
        """Minutes in (start, end] where this routine may change state (jittered block edges)."""
        points = set()
        for day in range(world.day_index(start) - 1, world.day_index(end) + 1):
            for block in self.blocks:
                j_start, j_end = self._jitter(block, day, character_id, seed)
                s = world.absolute_minute(day, block.start) + j_start
                e = world.absolute_minute(day, block.end) + j_end
                if world.absolute_minute(day, block.end) <= world.absolute_minute(day, block.start):
                    e += MINUTES_PER_DAY
                points.update(p for p in (s, e) if start < p <= end)
        return sorted(points)

    def to_dict(self) -> dict[str, Any]:
        return {"home": self.home, "free_place": self.free_place, "blocks": [b.to_dict() for b in self.blocks]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Routine":
        home = str(data.get("home") or "")
        return cls(blocks=[RoutineBlock.from_dict(b, home) for b in data.get("blocks") or []], home=home,
                   free_place=str(data.get("free_place") or ""))


def build_routine(character_cfg: dict[str, Any], templates: dict[str, Any], home: str) -> Routine:
    """Story data -> Routine: template blocks + character blocks + default sleep unless overridden."""
    blocks: list[RoutineBlock] = []
    template = templates.get(str(character_cfg.get("template") or ""), {}) if templates else {}
    for raw in list(template.get("blocks") or []) + list(character_cfg.get("blocks") or []):
        blocks.append(RoutineBlock.from_dict(raw, home))
    if not any(b.availability == "asleep" for b in blocks) and home:
        blocks = default_blocks(home) + blocks
    free_place = str(character_cfg.get("free_place") or template.get("free_place") or "")
    return Routine(blocks=blocks, home=home, free_place=free_place)
