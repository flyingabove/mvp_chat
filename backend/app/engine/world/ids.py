from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocationId:
    """Type-safe wrapper around a location identifier.

    We keep IDs as strings in storage/JSON, but we pass them around as a
    value-object to make interfaces clearer and reduce mixups.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("LocationId must be a non-empty string")

    def __str__(self) -> str:
        return self.value
