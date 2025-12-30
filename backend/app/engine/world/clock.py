from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorldClock:
    """Single source of truth for world time.

    Stores minutes since world start. The rest of the system must advance time
    only through this class.
    """

    _minute: int = 0

    def __init__(self, start_minute: int = 0):
        if not isinstance(start_minute, int):
            raise TypeError("start_minute must be int")
        if start_minute < 0:
            raise ValueError("start_minute must be >= 0")
        self._minute = start_minute

    def now_minute(self) -> int:
        return self._minute

    def advance_minutes(self, minutes: int) -> None:
        if not isinstance(minutes, int):
            raise TypeError("minutes must be an int")
        if minutes <= 0:
            raise ValueError("Time advance must be positive")
        self._minute += minutes