# backend/app/engine/world/travel_resolver.py
from typing import Optional
from .graph import WorldGraph
from .clock import WorldClock
from .travel_rules import TravelRules
from .exposure import ExposureResolver, TravelExposure


class TravelResolver:
    """
    Executes travel from A to B:
    - resolves forks
    - advances time
    - produces exposure packet
    """

    def __init__(
        self,
        graph: WorldGraph,
        clock: WorldClock,
        rules: TravelRules,
        exposure_resolver: ExposureResolver,
    ):
        self.graph = graph
        self.clock = clock
        self.rules = rules
        self.exposure_resolver = exposure_resolver

    def resolve(self, from_id: str, to_id: str) -> TravelExposure:
        edges = self.graph.get_neighbors(from_id)
        chosen_edge = self.rules.choose_edge(
            [e for e in edges if e.to_id == to_id or True]
        )

        # EXIT_ORIGIN
        self.clock.advance(1)

        # TRANSIT
        self.clock.advance(chosen_edge.minutes)

        # ENTER_DESTINATION
        exposure = self.exposure_resolver.roll(
            intermediate_id=None
        )

        return exposure
