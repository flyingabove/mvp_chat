from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .ids import LocationId


@dataclass(frozen=True)
class ExposureConfig:
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
class ExposurePacket:
    """What the AI is allowed to know about travel for this turn."""

    exit_event_at_A: bool
    pass_intermediate_C: bool
    event_at_C: bool
    enter_event_at_B: bool
    describe_B: bool

    intermediate_id: Optional[LocationId] = None


class ExposureResolver:
    """Produces exposure packets according to the agreed p-slot rules."""

    def __init__(self, config: ExposureConfig, seed: int):
        config.validate()
        self._config = config
        self._seed = seed

    def _rng(self):
        import random

        return random.Random(self._seed)

    def roll(self, intermediate_id: Optional[LocationId]) -> ExposurePacket:
        r = self._rng()

        exit_event = r.random() < self._config.p_exit_A

        # If there is no intermediate in the chosen route, C cannot be exposed.
        if intermediate_id is None:
            return ExposurePacket(
                exit_event_at_A=exit_event,
                pass_intermediate_C=False,
                event_at_C=False,
                enter_event_at_B=(r.random() < self._config.p_enter_B),
                describe_B=(r.random() < self._config.p_describe_B),
                intermediate_id=None,
            )

        pass_c = r.random() < self._config.p_pass_C
        event_c = pass_c and (r.random() < self._config.p_event_at_C)

        return ExposurePacket(
            exit_event_at_A=exit_event,
            pass_intermediate_C=pass_c,
            event_at_C=event_c,
            enter_event_at_B=(r.random() < self._config.p_enter_B),
            describe_B=(r.random() < self._config.p_describe_B),
            intermediate_id=(intermediate_id if pass_c else None),
        )