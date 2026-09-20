"""Day/schedule primitive shared by cast-lifecycle scheduling (Phase 2) and,
eventually, routines/commitments (Phase 3). Deliberately minimal: a
day-boundary function derived from the existing absolute world minute, and a
generic pending-event record persisted on GameState. Neither concept is tied
to cast lifecycle specifically - `event_type` distinguishes what a given
pending event is for, the same way `transient_entries` is one list filtered
by namespace/scope rather than a separate list per purpose.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

MINUTES_PER_DAY = 1440


def day_number(minute: int) -> int:
    """0-based day index derived from an absolute world minute."""
    return max(0, int(minute or 0)) // MINUTES_PER_DAY


@dataclass
class PendingEvent:
    event_id: str
    event_type: str
    scheduled_day: int
    payload: dict[str, Any] = field(default_factory=dict)
    created_minute: int = 0
    status: str = "pending"
    applied_minute: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "scheduled_day": self.scheduled_day,
            "payload": dict(self.payload),
            "created_minute": self.created_minute,
            "status": self.status,
            "applied_minute": self.applied_minute,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PendingEvent":
        event_id = str(data.get("event_id") or "").strip()
        event_type = str(data.get("event_type") or "").strip()
        if not event_id or not event_type:
            raise ValueError("pending event requires event_id and event_type")
        applied_minute = data.get("applied_minute")
        return cls(
            event_id=event_id,
            event_type=event_type,
            scheduled_day=int(data.get("scheduled_day") or 0),
            payload=dict(data.get("payload") or {}),
            created_minute=int(data.get("created_minute") or 0),
            status=str(data.get("status") or "pending"),
            applied_minute=int(applied_minute) if applied_minute is not None else None,
        )
