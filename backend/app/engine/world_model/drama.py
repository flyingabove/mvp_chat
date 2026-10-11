"""Causal conflict threads; scene selection cannot invent or resolve a cause."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Optional


@dataclass
class ConflictThread:
    id: str
    participants: tuple[str, ...]
    cause_event_id: str
    opened_minute: int
    surface: str
    stage: str = "unresolved"
    last_focus_day: Optional[int] = None
    resolution_event_id: str = ""
    apology_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "participants": list(self.participants), "cause_event_id": self.cause_event_id,
                "opened_minute": self.opened_minute, "surface": self.surface, "stage": self.stage,
                "last_focus_day": self.last_focus_day, "resolution_event_id": self.resolution_event_id,
                "apology_by": self.apology_by}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ConflictThread":
        return cls(str(raw["id"]), tuple(raw.get("participants") or ()),
                   str(raw.get("cause_event_id") or ""), int(raw.get("opened_minute") or 0),
                   str(raw.get("surface") or ""), str(raw.get("stage") or "unresolved"),
                   raw.get("last_focus_day"), str(raw.get("resolution_event_id") or ""),
                   str(raw.get("apology_by") or ""))


@dataclass
class DramaBook:
    threads: list[ConflictThread] = field(default_factory=list)

    def get(self, thread_id: str) -> ConflictThread:
        return next(thread for thread in self.threads if thread.id == thread_id)

    def to_dict(self) -> dict[str, Any]:
        return {"threads": [thread.to_dict() for thread in self.threads]}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DramaBook":
        return cls([ConflictThread.from_dict(thread) for thread in raw.get("threads") or []])


def register_conflict(book: DramaBook, participants: Iterable[str], cause_event_id: str,
                      minute: int, surface: str) -> ConflictThread:
    participants = tuple(sorted(set(participants)))
    if len(participants) < 2 or not cause_event_id or not surface:
        raise ValueError("conflict requires participants, a real cause and a visible surface")
    existing = next((thread for thread in book.threads if thread.cause_event_id == cause_event_id), None)
    if existing is not None:
        return existing
    thread = ConflictThread(f"C{len(book.threads) + 1}", participants, cause_event_id, minute, surface)
    book.threads.append(thread)
    return thread


def choose_conflict(book: DramaBook, present: set[str], day: int) -> Optional[ConflictThread]:
    eligible = [thread for thread in book.threads if thread.stage == "unresolved"
                and set(thread.participants) <= present and thread.last_focus_day != day]
    if not eligible:
        return None
    chosen = sorted(eligible, key=lambda thread: (thread.opened_minute, thread.id))[0]
    chosen.last_focus_day = day
    return chosen


def repair_conflict(book: DramaBook, thread_id: str, resolution_event_id: str, minute: int) -> ConflictThread:
    thread = book.get(thread_id)
    if not resolution_event_id or minute < thread.opened_minute:
        raise ValueError("repair requires a later event")
    if thread.stage != "resolved":
        thread.stage, thread.resolution_event_id = "resolved", resolution_event_id
    return thread


_APOLOGY = re.compile(r"^I(?:'m| am) sorry\b|^I apologize\b", re.I)
_FORGIVE = re.compile(r"^I forgive you\b|^I accept your apology\b", re.I)


def record_repair_dialogue(model: Any, player_message: str, segments: list[dict]) -> list[str]:
    """Repair only from direct, audible decisions by the actual participants."""
    present = set(model.present_with_player()) | {"player"}
    utterances = [("player", player_message)] + [
        (segment.get("speaker_id"), segment.get("text") or "")
        for segment in segments or [] if segment.get("kind") == "dialogue"
    ]
    repaired: list[str] = []
    for thread in model.drama.threads:
        if thread.stage not in {"unresolved", "apology_offered"} or not set(thread.participants) <= present:
            continue
        for actor, text in utterances:
            if actor in thread.participants and _APOLOGY.match(str(text).strip()):
                if thread.apology_by == actor:
                    break
                event = model.world.add_event(model.world.minute, model.player_place(), thread.participants,
                                              f"@{actor} apologized about the conflict",
                                              kind="apology", operation_id=f"apology:{thread.id}:{model.turn}:{actor}",
                                              cause_ids=(thread.cause_event_id,))
                thread.stage, thread.apology_by = "apology_offered", actor
                break
        if not thread.apology_by:
            continue
        for actor, text in utterances:
            if actor in thread.participants and actor != thread.apology_by and _FORGIVE.match(str(text).strip()):
                event = model.world.add_event(model.world.minute, model.player_place(), thread.participants,
                                              f"@{actor} accepted @{thread.apology_by}'s apology",
                                              kind="reconciliation",
                                              operation_id=f"reconciliation:{thread.id}:{model.turn}:{actor}",
                                              cause_ids=(thread.cause_event_id,))
                repair_conflict(model.drama, thread.id, event.id, model.world.minute)
                repaired.append(thread.id)
                break
    return repaired
