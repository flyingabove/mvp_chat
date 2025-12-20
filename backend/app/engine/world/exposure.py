# backend/app/engine/world/exposure.py
import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class TravelExposure:
    exit_event: bool
    pass_intermediate: bool
    event_at_intermediate: bool
    enter_event: bool
    describe_destination: bool
    intermediate_id: Optional[str] = None


class ExposureResolver:
    def __init__(self, seed: int, probs: dict):
        self.random = random.Random(seed)
        self.probs = probs

    def roll(self, intermediate_id: Optional[str]) -> TravelExposure:
        pass_c = (
            intermediate_id is not None
            and self.random.random() < self.probs["p_pass_C"]
        )

        event_c = (
            pass_c
            and self.random.random() < self.probs["p_event_at_C"]
        )

        return TravelExposure(
            exit_event=self.random.random() < self.probs["p_exit_A"],
            pass_intermediate=pass_c,
            event_at_intermediate=event_c,
            enter_event=self.random.random() < self.probs["p_enter_B"],
            describe_destination=self.random.random() < self.probs["p_describe_B"],
            intermediate_id=intermediate_id if pass_c else None,
        )
