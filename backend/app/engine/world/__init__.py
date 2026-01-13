"""World/time system v2.

This package is a **self-contained** implementation of the agreed world-map rules:

- Graph-based world (topological, no coordinates)
- Discrete travel phases: EXIT(A) → TRANSIT → ENTER(B/C)
- Rule-driven, seeded route choice (the user is never asked)
- Probabilistic exposure packet controls what the AI may know about travel

Important:
- This package is intentionally **not integrated** into the current live game
  code paths yet. It exists to be validated by an integration test.
"""

from .ids import LocationId
from .clock import WorldClock
from .location import Location
from .edge import PathEdge
from .graph import WorldGraph
from .exposure import ExposureConfig, ExposurePacket, ExposureResolver, TravelExposure
from .travel_rules import TravelRules
from .travel_resolver import TravelRequest, TravelResult, TravelResolver
from .world_json import WorldDefinition, WorldDefinitionLoader

__all__ = [
    "LocationId",
    "WorldClock",
    "Location",
    "PathEdge",
    "WorldGraph",
    "ExposureConfig",
    "ExposurePacket",
    "ExposureResolver",
    "TravelExposure",
    "TravelRules",
    "TravelRequest",
    "TravelResult",
    "TravelResolver",
    "WorldDefinition",
    "WorldDefinitionLoader",
]
