"""Personal threads: arcs that move forward on the clock whether or not the
player is there (an audition, a job decision, a cover story under strain)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel


@dataclass
class Milestone:
    id: str
    day: int                      # calendar day index, 0 = the story's start date
    time: str                     # "HH:MM"
    text: str                     # world truth; may use @ids
    visibility: str = "private"   # public milestones leave a trace the player can notice
    trace: str = ""               # what a person present could notice ("Momoka is stretching in the hallway")
    memory_for: list[str] = field(default_factory=list)
    place: str = ""               # where it happens / where its trace shows ("" = wherever the owner is)
    fired: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "day": self.day, "time": self.time, "text": self.text,
                "visibility": self.visibility, "trace": self.trace, "memory_for": list(self.memory_for),
                "place": self.place, "fired": self.fired}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Milestone":
        return cls(id=str(data["id"]), day=int(data.get("day") or 0), time=str(data.get("time") or "12:00"),
                   text=str(data.get("text") or ""), visibility=str(data.get("visibility") or "private"),
                   trace=str(data.get("trace") or ""), memory_for=list(data.get("memory_for") or []),
                   place=str(data.get("place") or ""), fired=bool(data.get("fired")))


@dataclass
class Thread:
    id: str
    owner: str
    title: str
    topics: list[str] = field(default_factory=list)   # words that make the owner want to talk about it
    milestones: list[Milestone] = field(default_factory=list)

    @property
    def next_open(self) -> Milestone | None:
        return next((m for m in self.milestones if not m.fired), None)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "owner": self.owner, "title": self.title, "topics": list(self.topics),
                "milestones": [m.to_dict() for m in self.milestones]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Thread":
        return cls(id=str(data["id"]), owner=str(data["owner"]), title=str(data.get("title") or ""),
                   topics=list(data.get("topics") or []),
                   milestones=[Milestone.from_dict(m) for m in data.get("milestones") or []])


def advance_threads(model: "WorldModel", start: int, end: int) -> list[tuple[Thread, Milestone]]:
    """Fire every milestone whose time falls in (start, end], in chronological order.

    Only threads whose owner currently lives in the world advance; each fired
    milestone becomes an immutable event plus memories for the owner and the
    people it names in `memory_for`. Nobody else learns of it here.
    """
    due = []
    for thread in model.threads:
        if thread.owner not in model.characters:
            continue
        for milestone in thread.milestones:
            if milestone.fired:
                continue
            at = model.world.absolute_minute(milestone.day, milestone.time)
            if start < at <= end:
                due.append((at, thread, milestone))
    due.sort(key=lambda row: row[0])
    fired = []
    for at, thread, milestone in due:
        place = milestone.place or model.world.place_of(thread.owner) or ""
        knowers = [thread.owner] + [k for k in milestone.memory_for if k in model.characters or k == "player"]
        event = model.world.add_event(at, place, knowers, milestone.text, kind="milestone",
                                      visibility=milestone.visibility)
        for owner in dict.fromkeys(knowers):
            model.memories.add(owner, milestone.text, "witnessed", at, event_id=event.id,
                               private=milestone.visibility == "private")
        milestone.fired = True
        if milestone.visibility == "public" and milestone.trace:
            model.add_trace(at, place, milestone.trace)
        fired.append((thread, milestone))
    return fired


def active_thread_topics(model: "WorldModel", character_id: str) -> set[str]:
    topics: set[str] = set()
    for thread in model.threads:
        if thread.owner == character_id and thread.next_open is not None:
            topics.update(t.lower() for t in thread.topics)
    return topics
