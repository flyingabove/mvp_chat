# backend/app/engine/time_utils.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class WorldTimestamp:
    """A readable world timestamp."""

    # ISO-like string for debugging/logging
    iso: str
    # Human-friendly string shown to readers
    display: str


class WorldTimeFormatter:
    """
    Formats world time.

    We store the world start datetime on the state as a string:
        "YYYY-MM-DD hh:mm AM" (12-hour, with AM/PM)
    and advance by state.minute.
    """

    DEFAULT_START = "2025-01-01 08:00 PM"

    @classmethod
    def compute(cls, start_dt_str: str, minute: int) -> WorldTimestamp:
        start_str = (start_dt_str or "").strip() or cls.DEFAULT_START
        # Accept a couple common formats, but keep output stable.
        # Primary expected format: "YYYY-MM-DD hh:mm AM"
        parsed = None
        for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(start_str, fmt)
                break
            except Exception:
                continue

        if parsed is None:
            # Fallback to default if input is bad.
            parsed = datetime.strptime(cls.DEFAULT_START, "%Y-%m-%d %I:%M %p")

        dt = parsed + timedelta(minutes=int(minute or 0))
        display = dt.strftime("%Y-%m-%d %I:%M %p")
        iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        return WorldTimestamp(iso=iso, display=display)
