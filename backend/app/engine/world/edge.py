# backend/app/engine/world/edge.py
from dataclasses import dataclass


@dataclass(frozen=True)
class PathEdge:
    from_id: str
    to_id: str
    minutes: int
    is_transit: bool = False
    blocked: bool = False
