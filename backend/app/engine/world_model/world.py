"""World truth: where every entity is, the clock, and committed events.

`where` is the single source of location. `contents` is derived from it and
kept in sync only by `move()` / `remove()`; it is never saved, so a save can
never disagree with itself. A location may be a place ID from the story world
graph or another entity (a container: letter -> drawer -> study).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from backend.app.engine.world_model.entities import Entity
from backend.app.engine.world_model.events import Event

MINUTES_PER_DAY = 1440
DEFAULT_START = datetime(2000, 1, 1, 9, 0)


def parse_start(value: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).strip()) if value else DEFAULT_START
    except ValueError:
        return DEFAULT_START


def parse_hhmm(value: str) -> int:
    """'07:30' -> 450 minutes after midnight."""
    hours, _, minutes = str(value).strip().partition(":")
    total = int(hours) * 60 + int(minutes or 0)
    if not 0 <= total <= MINUTES_PER_DAY:
        raise ValueError(f"time of day out of range: {value!r}")
    return total % MINUTES_PER_DAY


class World:
    def __init__(self, start_datetime: str = "", minute: int = 0,
                 where: Optional[dict[str, str]] = None,
                 entities: Optional[Iterable[Entity]] = None,
                 events: Optional[Iterable[Event]] = None) -> None:
        self.start_datetime = start_datetime
        self.minute = int(minute or 0)
        self.entities: dict[str, Entity] = {e.id: e for e in (entities or [])}
        self.where: dict[str, str] = {}
        self._contents: dict[str, set[str]] = {}
        self.events: list[Event] = list(events or [])
        for entity_id, place in (where or {}).items():
            self.move(entity_id, place)

    # -- location ------------------------------------------------------------
    def move(self, entity_id: str, to: str) -> Optional[str]:
        """The only writer of location. Returns the previous location."""
        if not entity_id or not to:
            raise ValueError("move requires an entity id and a destination")
        if to == entity_id or entity_id in self._container_chain(to):
            raise ValueError(f"{entity_id!r} cannot be placed inside itself")
        previous = self.where.get(entity_id)
        if previous is not None:
            self._contents.get(previous, set()).discard(entity_id)
        self.where[entity_id] = to
        self._contents.setdefault(to, set()).add(entity_id)
        return previous

    def remove(self, entity_id: str) -> None:
        previous = self.where.pop(entity_id, None)
        if previous is not None:
            self._contents.get(previous, set()).discard(entity_id)

    def where_is(self, entity_id: str) -> Optional[str]:
        return self.where.get(entity_id)

    def place_of(self, entity_id: str) -> Optional[str]:
        """The world place an entity is in, looking through containers."""
        location = self.where.get(entity_id)
        seen: set[str] = set()
        while location in self.where and location not in seen:
            seen.add(location)
            location = self.where[location]
        return location

    def contents_of(self, place: str, recursive: bool = False) -> set[str]:
        direct = set(self._contents.get(place, set()))
        if not recursive:
            return direct
        found, frontier = set(direct), list(direct)
        while frontier:
            inner = self._contents.get(frontier.pop(), set()) - found
            found |= inner
            frontier.extend(inner)
        return found

    def _container_chain(self, location: str) -> list[str]:
        chain, seen = [], set()
        while location in self.where and location not in seen:
            seen.add(location)
            chain.append(location)
            location = self.where[location]
        return chain

    # -- events ----------------------------------------------------------------
    def add_event(self, minute: int, place: str, participants: Iterable[str], truth: str,
                  kind: str = "scene", visibility: str = "private", operation_id: str = "",
                  payload: Optional[dict[str, Any]] = None, cause_ids: Iterable[str] = ()) -> Event:
        """Commit an immutable event with a monotonic ID (stable across save/replay)."""
        participants = tuple(participants)
        cause_ids = tuple(cause_ids)
        payload = dict(payload or {})
        if operation_id:
            prior = next((e for e in self.events if e.operation_id == operation_id), None)
            if prior is not None:
                if (prior.minute, prior.place, prior.participants, prior.truth, prior.kind,
                        prior.visibility, prior.payload, prior.cause_ids) != (
                        int(minute), place, participants, truth, kind, visibility, payload, cause_ids):
                    raise ValueError("operation ID reused with different event content")
                return prior
        event = Event(id=f"E{len(self.events) + 1}", minute=int(minute), place=place,
                      participants=participants, truth=truth, kind=kind, visibility=visibility,
                      operation_id=operation_id, payload=payload, cause_ids=cause_ids)
        self.events.append(event)
        return event

    def shared_events(self, a: str, b: str) -> list[Event]:
        """Do A and B share a past? A query, never a stored edge."""
        return [e for e in self.events if a in e.participants and b in e.participants]

    # -- clock -----------------------------------------------------------------
    def datetime_at(self, minute: Optional[int] = None) -> datetime:
        return parse_start(self.start_datetime) + timedelta(minutes=self.minute if minute is None else minute)

    def minute_of_day(self, minute: Optional[int] = None) -> int:
        moment = self.datetime_at(minute)
        return moment.hour * 60 + moment.minute

    def day_index(self, minute: Optional[int] = None) -> int:
        """0 on the start date, 1 the next calendar day, ..."""
        start = parse_start(self.start_datetime)
        return (self.datetime_at(minute).date() - start.date()).days

    def weekday(self, minute: Optional[int] = None) -> int:
        return self.datetime_at(minute).weekday()

    def absolute_minute(self, day: int, hhmm: str) -> int:
        """Game minute for calendar day `day` (0 = start date) at `hhmm`."""
        start = parse_start(self.start_datetime)
        target = datetime.combine(start.date() + timedelta(days=int(day)), datetime.min.time()) \
            + timedelta(minutes=parse_hhmm(hhmm))
        return int((target - start).total_seconds() // 60)

    def next_minute_at(self, hhmm: str, after: Optional[int] = None) -> int:
        """First game minute strictly after `after` whose time of day is `hhmm`."""
        after = self.minute if after is None else after
        day = self.day_index(after)
        candidate = self.absolute_minute(day, hhmm)
        return candidate if candidate > after else self.absolute_minute(day + 1, hhmm)

    # -- persistence -----------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"start_datetime": self.start_datetime, "minute": self.minute,
                "where": dict(self.where), "entities": [e.to_dict() for e in self.entities.values()],
                "events": [e.to_dict() for e in self.events]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "World":
        return cls(start_datetime=str(data.get("start_datetime") or ""), minute=int(data.get("minute") or 0),
                   where=dict(data.get("where") or {}),
                   entities=[Entity.from_dict(e) for e in data.get("entities") or []],
                   events=[Event.from_dict(e) for e in data.get("events") or []])
