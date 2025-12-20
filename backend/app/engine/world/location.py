# backend/app/engine/world/location.py
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    description: str
    tags: List[str]

    allows_phone: bool = True
    is_transit: bool = False
