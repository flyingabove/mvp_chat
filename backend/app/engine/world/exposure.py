from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .ids import LocationId


@dataclass(frozen=True)
class ExposureConfig:
    """Probability slots for travel exposure.

    These match the naming used in the design doc/tests:
    - A = origin
    - C = optional intermediate
    - B = destination
    """

    p_exit_A: float
    p_pass_C: float
    p_event_at_C: float
    p_enter_B: float
    p_describe_B: float

    def validate(self) -> None:
        for name, value in (
            ("p_exit_A", self.p_exit_A),
            ("p_pass_C", self.p_pass_C),
            ("p_event_at_C", self.p_event_at_C),
            ("p_enter_B", self.p_enter_B),
            ("p_describe_B", self.p_describe_B),
        ):
            if not (0.0 <= float(value) <= 1.0):
                raise ValueError(f"{name} must be in [0,1]")


@dataclass(frozen=True)
class TravelExposure:
    """What the AI is allowed to know about a travel event.

    Fields use short, readable names (A = origin, C = intermediate, B = destination).
    """

    exit_event: bool
    pass_intermediate: bool
    event_at_intermediate: bool
    enter_event: bool
    describe_destination: bool
    intermediate_id: Optional[LocationId] = None


class ExposureResolver:
    """Produces exposure packets according to the agreed p-slot rules."""

    def __init__(
        self,
        config: ExposureConfig | None = None,
        seed: int = 0,
        *,
        probs: dict | None = None,
    ) -> None:
        """Create an exposure resolver.

        New-style usage:
            ExposureResolver(config=ExposureConfig(...), seed=seed)

        Back-compat usage (older tests / callers):
            ExposureResolver(seed=seed, probs={...})
        """

        if config is None:
            if probs is None:
                raise TypeError("ExposureResolver requires `config` or `probs`")
            config = ExposureConfig(
                p_exit_A=float(probs.get("p_exit_A", 0.2)),
                p_pass_C=float(probs.get("p_pass_C", 0.5)),
                p_event_at_C=float(probs.get("p_event_at_C", 0.25)),
                p_enter_B=float(probs.get("p_enter_B", 0.2)),
                p_describe_B=float(probs.get("p_describe_B", 0.6)),
            )

        config.validate()
        self._config = config
        self._seed = int(seed)

    def _rng(self):
        import random

        return random.Random(self._seed)

    def roll(self, intermediate_id: Optional[LocationId]) -> TravelExposure:
        """Return a TravelExposure describing what the AI may know about this travel event."""

        r = self._rng()

        exit_event = r.random() < self._config.p_exit_A

        if intermediate_id is None:
            return TravelExposure(
                exit_event=exit_event,
                pass_intermediate=False,
                event_at_intermediate=False,
                enter_event=(r.random() < self._config.p_enter_B),
                describe_destination=(r.random() < self._config.p_describe_B),
                intermediate_id=None,
            )

        pass_c = r.random() < self._config.p_pass_C
        event_c = pass_c and (r.random() < self._config.p_event_at_C)

        return TravelExposure(
            exit_event=exit_event,
            pass_intermediate=pass_c,
            event_at_intermediate=event_c,
            enter_event=(r.random() < self._config.p_enter_B),
            describe_destination=(r.random() < self._config.p_describe_B),
            intermediate_id=(intermediate_id if pass_c else None),
        )
