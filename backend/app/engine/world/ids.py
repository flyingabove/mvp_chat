from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class LocationId:
    value: str

    """Type-safe wrapper around a location identifier.

    We keep IDs as strings in storage/JSON, but we pass them around as a
    value-object to make interfaces clearer and reduce mixups.
    """

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other) -> bool:
        if isinstance(other, LocationId):
            return self.value == other.value
        if isinstance(other, str):
            return self.value == other
        return False

    def __hash__(self) -> int:
        return hash(self.value)
