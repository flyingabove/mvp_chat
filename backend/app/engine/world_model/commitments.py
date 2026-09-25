"""Promises are memories with a due time. Nothing is invented: a housemate only
points at a covered plate if they actually promised to save dinner."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from backend.app.engine.world_model.memory import Memory

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

# Conservative: first-person future statement + an explicit time phrase.
PROMISE = re.compile(
    r"\bI(?:'ll| will| promise(?: to| I'll)?| am going to|'m going to)\s+"
    r"(?P<what>[^.!?\n]{3,90}?)\s*"
    r"(?P<when>tomorrow(?: morning| afternoon| evening| night)?|tonight|this (?:morning|afternoon|evening)|"
    r"later(?: today| tonight)?|after (?:dinner|work|class|practice)|at \d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b",
    re.I)
EXPIRE_AFTER_MIN = 12 * 60


def due_minute(model: "WorldModel", when: str, now: int) -> int:
    world, when = model.world, when.lower().strip()
    if when.startswith("tomorrow"):
        part = when.replace("tomorrow", "").strip() or "morning"
        hhmm = {"morning": "09:00", "afternoon": "14:00", "evening": "19:00", "night": "21:00"}.get(part, "09:00")
        return world.absolute_minute(world.day_index(now) + 1, hhmm)
    if when in ("tonight", "later tonight", "this evening"):
        target = world.absolute_minute(world.day_index(now), "20:00")
        return target if target > now else now + 60
    if when == "this morning":
        return max(now + 30, world.absolute_minute(world.day_index(now), "11:00"))
    if when == "this afternoon":
        return max(now + 30, world.absolute_minute(world.day_index(now), "15:00"))
    if when.startswith("after "):
        return now + {"dinner": 90, "work": 8 * 60, "class": 3 * 60, "practice": 3 * 60}.get(when[6:], 120)
    if when.startswith("at "):
        match = re.match(r"at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?", when)
        hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
        if meridiem == "pm" and hour < 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        return world.next_minute_at(f"{hour % 24:02d}:{minute:02d}", now)
    return now + 180            # "later", "later today"


def add_commitment(model: "WorldModel", owner: str, counterpart: str, what: str, due: int,
                   minute: int) -> tuple[Memory, Memory]:
    """Record a promise for BOTH parties (each remembers it from their side)."""
    own = model.memories.add(owner, f"I promised @{counterpart} to {what}", "promised", minute,
                             kind="promise", due=due, counterpart=counterpart)
    other = model.memories.add(counterpart, f"@{owner} promised to {what}", f"told_by:{owner}", minute,
                               kind="promise", due=due, counterpart=owner)
    return own, other


def detect_promises(model: "WorldModel", speaker: str, listener: str, text: str, minute: int) -> list[Memory]:
    """Find explicit time-bound promises in `speaker`'s words and record them."""
    created = []
    for match in PROMISE.finditer(text or ""):
        what = re.sub(r"^(?:to|be)\s+", "", re.sub(r"\s+", " ", match.group("what")).strip(" ,"), flags=re.I)
        when = match.group("when")
        promise_text = f"{what} {when}".strip()
        if any(m.kind == "promise" and m.status == "open" and promise_text in m.text
               for m in model.memories.of(speaker)):
            continue
        own, _ = add_commitment(model, speaker, listener, promise_text, due_minute(model, when, minute), minute)
        created.append(own)
    return created


def due_commitments(model: "WorldModel", now: int, owner: Optional[str] = None) -> list[Memory]:
    """Open promises (from the promiser's side) that are due now or overdue but not expired."""
    return [m for m in model.memories.open_promises(owner)
            if m.source == "promised" and m.due is not None and m.due <= now < m.due + EXPIRE_AFTER_MIN]


def expire_commitments(model: "WorldModel", now: int) -> list[Memory]:
    expired = []
    for memory in model.memories.open_promises():
        if memory.due is not None and now >= memory.due + EXPIRE_AFTER_MIN:
            memory.status = "broken"
            expired.append(memory)
    return expired


def resolve_commitment(memory: Memory, kept: bool = True) -> None:
    memory.status = "kept" if kept else "broken"
