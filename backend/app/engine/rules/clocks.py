"""Story clocks: a counter over committed events with a warning beat and a trigger.

Declared in story JSON (`clocks`). The counter is kept by engine code (for
example `couples_left`, incremented only by other couples' departures). The
warning beat fires once; reaching the trigger fires its beat once, and the
matching ending (a `counter_at_least` condition in `endings`) ends the run.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Clock:
    id: str
    counter: str
    warn_at: int
    trigger_at: int
    warn_beat: str
    trigger_beat: str


def clocks_for(story_cfg: dict[str, Any]) -> list[Clock]:
    clocks = []
    for raw in (story_cfg or {}).get("clocks") or []:
        clock = Clock(str(raw.get("id") or ""), str(raw.get("counter") or ""), int(raw.get("warn_at") or 0),
                      int(raw.get("trigger_at") or 0), str(raw.get("warn_beat") or ""),
                      str(raw.get("trigger_beat") or ""))
        if not clock.id or not clock.counter or clock.trigger_at < 1:
            raise ValueError(f"clock needs id, counter and trigger_at >= 1: {raw}")
        if clock.warn_at and not 0 < clock.warn_at < clock.trigger_at:
            raise ValueError(f"clock {clock.id!r} warn_at must be below trigger_at")
        clocks.append(clock)
    if len({c.id for c in clocks}) != len(clocks):
        raise ValueError("clock ids must be unique")
    return clocks


def due_beats(clocks: list[Clock], counters: dict[str, int]) -> list[tuple[str, str]]:
    """(marker key, beat text) for each warning/trigger reached and not yet delivered."""
    beats = []
    for clock in clocks:
        value = counters.get(clock.counter, 0)
        for stage, threshold, text in (("trigger", clock.trigger_at, clock.trigger_beat),
                                       ("warn", clock.warn_at, clock.warn_beat)):
            key = f"clock:{clock.id}:{stage}"
            if threshold and value >= threshold and text and not counters.get(key):
                beats.append((key, text))
                break
    return beats
