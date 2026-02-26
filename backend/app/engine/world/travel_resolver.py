from __future__ import annotations

from dataclasses import dataclass

from .clock import WorldClock
from .exposure import ExposureResolver, TravelExposure
from .graph import WorldGraph
from .ids import LocationId
from .travel_rules import TravelRoute, TravelRules


@dataclass(frozen=True)
class TravelRequest:
    """A travel intent derived from user text."""

    from_id: LocationId
    to_id: LocationId


@dataclass(frozen=True)
class TravelTiming:
    """Timing parameters for travel phases."""

    exit_minutes: int = 1

    def validate(self) -> None:
        if self.exit_minutes <= 0:
            raise ValueError("exit_minutes must be positive")


@dataclass(frozen=True)
class TravelResult:
    """Result of executing a travel request."""

    request: TravelRequest
    route: TravelRoute
    exposure: TravelExposure
    start_minute: int
    end_minute: int

    def minutes_spent(self) -> int:
        return self.end_minute - self.start_minute


class TravelResolver:
    """Executes travel according to the agreed rules.

    Invariants enforced:
    - Time always advances.
    - The chosen route is determined by TravelRules (seeded), not the user.
    - No events are "mid-edge": the exposure packet only exposes A-exit, C, B-enter.
    """

    def __init__(
        self,
        graph: WorldGraph,
        clock: WorldClock,
        rules: TravelRules,
        exposure_resolver: ExposureResolver,
        timing: TravelTiming | None = None,
    ) -> None:
        if timing is None:
            timing = TravelTiming()
        timing.validate()
        self._graph = graph
        self._clock = clock
        self._rules = rules
        self._exposure = exposure_resolver
        self._timing = timing

    def execute(self, request: TravelRequest) -> TravelResult:
        start_minute = self._clock.now_minute()

        # 1) Resolve route (direct or one-intermediate).
        route = self._rules.resolve_route(self._graph, request.from_id, request.to_id)
        intermediate_id = route.intermediate_id()  # LocationId | None

        # 2) EXIT A
        self._clock.advance_minutes(self._timing.exit_minutes)

        # 3) TRANSIT (one or two segments)
        for seg in route.segments:
            self._clock.advance_minutes(seg.edge.minutes)

        # 4) Exposure (what the AI is allowed to know)
        exposure = self._exposure.roll(intermediate_id=intermediate_id)

        end_minute = self._clock.now_minute()
        return TravelResult(
            request=request,
            route=route,
            exposure=exposure,
            start_minute=start_minute,
            end_minute=end_minute,
        )

    def resolve(self, from_id: str, to_id: str) -> TravelExposure:
        """Compatibility API for unit tests.

        Executes travel from `from_id` to `to_id` and returns a TravelExposure.
        New code should prefer `execute(TravelRequest(...))`.
        """
        result = self.execute(TravelRequest(LocationId(from_id), LocationId(to_id)))
        return result.exposure

    def current_minute(self) -> int:
        return self._clock.now_minute()