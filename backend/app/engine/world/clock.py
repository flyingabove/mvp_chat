# backend/app/engine/world/clock.py

class WorldClock:
    """
    Single source of truth for world time.
    Time is stored as minutes since world start.
    """

    def __init__(self, start_minute: int = 0):
        self._minute = start_minute

    @property
    def minute(self) -> int:
        return self._minute

    def advance(self, minutes: int) -> None:
        if minutes <= 0:
            raise ValueError("Time advance must be positive")
        self._minute += minutes
