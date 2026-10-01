"""SeasonRunner: run a whole story with no human player, offline (BL-86, P-04).

One day at a time: the existing stepper (`world_model/stepper.py`) advances the clock and moves every
character through their routine -- the player's slot included, since nothing here assumes a human drives
`PLAYER`; a scripted resident following a routine is handled identically to any NPC. Co-located awake pairs
form encounters with the same pairing rule `world_model/offscreen.py` uses for its dice mechanism (this
runner replaces that dice roll with a written scene, per BL-86; the dice path is untouched for ordinary
player turns). Each encounter up to the day's scene cap is written by the `Writer` and its extracted update
is committed through the model's own primitives -- `world.add_event`, `epistemics.observe_event`,
`memories.add`, relationship `adjust()` -- never a second engine. A update that names someone who was not in
the scene is grounding the runner cannot accept, so it is rejected rather than applied.

Hard caps: `scenes_per_day` bounds work within a day; `budget` bounds total writer calls across the whole
run and is checked *before* a scene is written, so a run never stops mid-write.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from backend.app.engine.cast_lifecycle import CastLifecycleState
from backend.app.engine.world_model.epistemics import observe_event
from backend.app.engine.world_model.model import WorldModel
from backend.app.engine.world_model.offscreen import Encounter, find_encounters
from backend.app.engine.world_model.stepper import step_world
from backend.app.sim.invariants import check_day
from backend.app.sim.writer import SceneUpdate, Writer

MINUTES_PER_DAY = 1440
DEFAULT_SCENES_PER_DAY = 3
DEFAULT_BUDGET = 1000


class Relationships(Protocol):
    def feelings(self, a: str, b: str) -> dict: ...
    def adjust(self, a: str, b: str, narrative: str = "", **deltas: float) -> None: ...


@dataclass
class Story:
    """Everything a SeasonRunner needs about a story beyond the world model itself."""
    model: WorldModel
    relationships: Relationships
    cast_lifecycle: Optional[CastLifecycleState] = None
    expected_cast_size: int = 6


@dataclass
class DayReport:
    day: int
    scenes_written: int = 0
    scenes_summarized: int = 0
    rejections: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


@dataclass
class SeasonResult:
    days: list[DayReport] = field(default_factory=list)
    calls_used: int = 0
    stopped_early: bool = False

    @property
    def completed_days(self) -> int:
        return len(self.days)

    @property
    def all_violations(self) -> list[str]:
        return [v for day in self.days for v in day.violations]

    @property
    def all_rejections(self) -> list[str]:
        return [r for day in self.days for r in day.rejections]


class SeasonRunner:
    """Advance `story` for `days` simulated days on `writer`, deterministic for a given `seed`."""

    def __init__(self, story: Story, seed: str, writer: Writer, days: int,
                scenes_per_day: int = DEFAULT_SCENES_PER_DAY, budget: int = DEFAULT_BUDGET) -> None:
        self.story = story
        self.seed = seed
        self.writer = writer
        self.days = days
        self.scenes_per_day = scenes_per_day
        self.budget = budget

    def run(self) -> SeasonResult:
        model = self.story.model
        result = SeasonResult()
        for day_index in range(self.days):
            start = model.world.minute
            end = start + MINUTES_PER_DAY
            step = step_world(model, start, end, scene_present=set())
            result.days.append(self._run_day(day_index, step, result))
            if result.stopped_early:
                break
        return result

    def _run_day(self, day_index: int, step, result: SeasonResult) -> DayReport:
        report = DayReport(day=day_index)
        for position, encounter in enumerate(find_encounters(step)):
            if position >= self.scenes_per_day:
                report.scenes_summarized += 1
                continue
            if result.calls_used >= self.budget:
                result.stopped_early = True
                break
            update = self._write_scene(encounter)
            result.calls_used += 1
            report.scenes_written += 1
            report.rejections.extend(self._commit_scene(encounter, update))
        report.violations.extend(check_day(self.story.model, self.story.cast_lifecycle,
                                           self.story.expected_cast_size))
        return report

    def _write_scene(self, encounter: Encounter) -> SceneUpdate:
        prompt = (f"Present: {encounter.a}, {encounter.b}\n"
                  f"Place: {encounter.place}\n"
                  f"Minute: {encounter.minute}\n"
                  "Write what happens between them.")
        return self.writer.extract(self.writer.write_scene(prompt))

    def _commit_scene(self, encounter: Encounter, update: SceneUpdate) -> list[str]:
        """Apply `update` through the model's own primitives; reject anything not grounded in `encounter`."""
        model = self.story.model
        participants = {encounter.a, encounter.b}
        rejected: list[str] = []
        event = model.world.add_event(encounter.minute, encounter.place, tuple(sorted(participants)),
                                      update.summary, kind="scene", visibility="public")
        for cid in participants:
            observe_event(model.epistemics, cid, event.id, "participant", event.truth, encounter.minute)
            model.memories.add(cid, event.truth, "witnessed", encounter.minute, event_id=event.id)
        for delta in update.relationship_deltas:
            if {delta.a, delta.b} - participants:
                rejected.append(f"relationship delta {delta.a}-{delta.b} not grounded in scene "
                                f"participants {sorted(participants)}")
                continue
            deltas = {k: v for k, v in (("trust_delta", delta.trust_delta), ("affection_delta", delta.affection_delta),
                                        ("suspicion_delta", delta.suspicion_delta), ("fear_delta", delta.fear_delta))
                     if v}
            if deltas:
                self.story.relationships.adjust(delta.a, delta.b, narrative=update.summary, **deltas)
        for cid, place in update.movements:
            if cid not in participants:
                rejected.append(f"movement for {cid!r} not grounded in scene participants {sorted(participants)}")
                continue
            model.world.move(cid, place)
        return rejected
