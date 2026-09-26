"""Promises are memories with a due time. Nothing is invented: a housemate only
points at a covered plate if they actually promised to save dinner.

Promises come from the turn extractor (CommitmentUpdate), which reads the whole
previous exchange; a regex detector was ~50% precise and missed accepted
requests ("Let's do it!") in live measurement (QC 2026-09-25)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from backend.app.engine.world_model.memory import Memory
from backend.app.engine.world_model.agreements import record_unilateral_promise, resolve as resolve_agreement
from backend.app.engine.world_model.model import PLAYER

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

EXPIRE_AFTER_MIN = 12 * 60


PARTS_OF_DAY = {"morning": "09:00", "afternoon": "14:00", "evening": "19:00", "night": "21:00", "noon": "12:00",
                "breakfast": "08:00", "lunch": "12:30", "dinner": "19:00"}
MEALS = {"breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner", "supper": "dinner"}
DUPLICATE_OVERLAP = 0.6
CLOCK = re.compile(r"\bat (\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b")
LATER_TODAY_MIN = 180


def _clock_hhmm(match: re.Match) -> str:
    hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return f"{hour % 24:02d}:{minute:02d}"


def due_minute(model: "WorldModel", when: str, now: int, what: str = "") -> int:
    """Map an extractor time phrase to a game minute ("tomorrow at 8", "tonight", "this weekend").

    Without a clock time or part of day, a meal in the promised action sets
    the time ("save you dinner" + "tomorrow" -> tomorrow 19:00, not 09:00)."""
    world, when = model.world, " ".join((when or "").lower().split())
    today = world.day_index(now)
    if when.startswith("after "):            # relative: "after dinner" is ~90 min from now, not 19:00
        return now + {"dinner": 90, "work": 8 * 60, "class": 3 * 60, "practice": 3 * 60}.get(when[6:], 120)
    clock = CLOCK.search(when)
    part = next((p for p in PARTS_OF_DAY if p in when), "")
    if not clock and not part:
        meal = next((m for m in MEALS if re.search(rf"\b{m}\b", (what or "").lower())), "")
        if meal:
            part = MEALS[meal]
    if "tomorrow" in when:
        hhmm = _clock_hhmm(clock) if clock else PARTS_OF_DAY.get(part, "09:00")
        return world.absolute_minute(today + 1, hhmm)
    if "weekend" in when:
        days_to_saturday = (5 - world.weekday(now)) % 7 or 7
        return world.absolute_minute(today + days_to_saturday, "12:00")
    if "next week" in when:
        return world.absolute_minute(today + 7, "12:00")
    if clock:
        return world.next_minute_at(_clock_hhmm(clock), now)
    if "tonight" in when or part in ("evening", "night"):
        target = world.absolute_minute(today, "20:00")
        return target if target > now else now + 60
    if part in ("morning", "afternoon", "noon", "breakfast", "lunch", "dinner"):
        target = world.absolute_minute(today, PARTS_OF_DAY[part])
        return target if target > now else world.absolute_minute(today + 1, PARTS_OF_DAY[part])
    return now + LATER_TODAY_MIN            # "later", "soon", unrecognized

def add_commitment(model: "WorldModel", owner: str, counterpart: str, what: str, due: int,
                   minute: int) -> tuple[Memory, Memory]:
    """Record a promise for BOTH parties (each remembers it from their side)."""
    agreement = record_unilateral_promise(model.agreements, owner, counterpart, what, due, minute)
    own = model.memories.add(owner, f"I promised @{counterpart} to {what}", "promised", minute,
                             kind="promise", due=due, counterpart=counterpart, agreement_id=agreement.id)
    other = model.memories.add(counterpart, f"@{owner} promised to {what}", f"told_by:{owner}", minute,
                               kind="promise", due=due, counterpart=owner, agreement_id=agreement.id)
    return own, other


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", (text or "").lower())) - {"a", "an", "the", "some", "you", "your", "to"}


def _flip_request(owner: str, counterpart: str, what: str) -> tuple[str, str, str]:
    """"Would you show me around?" accepted by an NPC sometimes comes back as the
    PLAYER promising "show me around": the doer is the other party."""
    if owner == PLAYER and re.search(r"\b(me|my)\b", what, re.I):
        what = re.sub(r"\bme\b", "you", re.sub(r"\bmy\b", "your", what, flags=re.I), flags=re.I)
        return counterpart, owner, what
    return owner, counterpart, what


def record_commitment(model: "WorldModel", owner: str, counterpart: str, what: str, when: str,
                      minute: int) -> Optional[Memory]:
    """Record an extracted promise once; people must both be in the world (or be the player)."""
    known = set(model.characters) | {PLAYER}
    if owner not in known or counterpart not in known or owner == counterpart or not what.strip():
        return None
    owner, counterpart, what = _flip_request(owner, counterpart, what.strip().rstrip("."))
    mine = _words(what)
    for m in model.memories.of(owner):
        if m.kind == "promise" and m.status == "open" and m.counterpart == counterpart:
            theirs = _words(m.text) - {"i", "promised"}
            if mine and len(mine & theirs) / len(mine | theirs or {""}) >= DUPLICATE_OVERLAP:
                return None
    own, _ = add_commitment(model, owner, counterpart, what, due_minute(model, when, minute, what), minute)
    return own


def due_commitments(model: "WorldModel", now: int, owner: Optional[str] = None) -> list[Memory]:
    """Open promises (from the promiser's side) that are due now or overdue but not expired."""
    return [m for m in model.memories.open_promises(owner)
            if m.source == "promised" and m.due is not None and m.due <= now < m.due + EXPIRE_AFTER_MIN]


def expire_commitments(model: "WorldModel", now: int) -> list[Memory]:
    expired = []
    for memory in model.memories.open_promises():
        if memory.due is not None and now >= memory.due + EXPIRE_AFTER_MIN:
            memory.status = "broken"
            if memory.agreement_id:
                agreement = model.agreements.get(memory.agreement_id)
                if agreement.status == "accepted":
                    # Passing the grace period without fulfillment is evidence
                    # for expiry, not proof that anyone deliberately broke it.
                    resolve_agreement(model.agreements, agreement.id, "expired", now)
            expired.append(memory)
    return expired


def resolve_commitment(memory: Memory, kept: bool = True) -> None:
    memory.status = "kept" if kept else "broken"
