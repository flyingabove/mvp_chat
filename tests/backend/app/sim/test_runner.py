"""SeasonRunner on the fake writer: the offline plumbing proof for BL-86/P-04."""
from __future__ import annotations

from dataclasses import replace

import pytest

from backend.app.sim.runner import SeasonRunner
from backend.app.sim.writer import FakeWriter, RelationshipDelta, SceneUpdate
from tests.backend.app.sim.helpers import build_story

DAYS = 5


class BrokenFakeWriter(FakeWriter):
    """A deliberately broken writer: invents a relationship change for someone who was never in the scene."""

    def extract(self, text: str) -> SceneUpdate:
        update = super().extract(text)
        ghost = RelationshipDelta("nobody_was_here", "also_not_here", affection_delta=0.9)
        return replace(update, relationship_deltas=update.relationship_deltas + (ghost,))


def test_five_day_season_completes_on_the_fake_writer() -> None:
    story = build_story()
    runner = SeasonRunner(story, seed="season-seed", writer=FakeWriter(), days=DAYS)
    result = runner.run()
    assert result.completed_days == DAYS
    assert not result.stopped_early
    assert result.calls_used > 0
    assert sum(day.scenes_written for day in result.days) == result.calls_used


def test_season_is_repeatable_given_the_same_seed() -> None:
    first = SeasonRunner(build_story("season-seed"), seed="season-seed", writer=FakeWriter(), days=DAYS).run()
    second = SeasonRunner(build_story("season-seed"), seed="season-seed", writer=FakeWriter(), days=DAYS).run()

    def fingerprint(result):
        return [(day.scenes_written, day.scenes_summarized, day.violations, day.rejections) for day in result.days]

    assert fingerprint(first) == fingerprint(second)
    assert first.calls_used == second.calls_used


def test_scenes_per_day_cap_is_respected() -> None:
    cap = 2
    story = build_story()
    runner = SeasonRunner(story, seed="season-seed", writer=FakeWriter(), days=DAYS, scenes_per_day=cap)
    result = runner.run()
    for day in result.days:
        assert day.scenes_written <= cap
    # Five residents + the player in one room all day: there is more to write than the cap allows.
    assert any(day.scenes_summarized > 0 for day in result.days)


def test_total_budget_cap_stops_the_run_cleanly() -> None:
    budget = 3
    story = build_story()
    runner = SeasonRunner(story, seed="season-seed", writer=FakeWriter(), days=DAYS, budget=budget)
    result = runner.run()
    assert result.calls_used <= budget
    assert result.stopped_early
    assert result.completed_days < DAYS or sum(d.scenes_written for d in result.days) <= budget


def test_no_invariant_is_ever_violated_on_the_fake_writer() -> None:
    story = build_story()
    runner = SeasonRunner(story, seed="season-seed", writer=FakeWriter(), days=DAYS)
    result = runner.run()
    assert result.all_violations == []


def test_broken_writer_fabrication_is_rejected_not_applied() -> None:
    """A writer that invents a relationship change for people who were never in the scene is caught.

    The runner must neither silently accept the fabrication into relationship state nor let it pass as a
    perceived memory; it is rejected and reported instead.
    """
    story = build_story()
    runner = SeasonRunner(story, seed="season-seed", writer=BrokenFakeWriter(), days=1)
    result = runner.run()

    assert any("nobody_was_here" in rejection for rejection in result.all_rejections)
    # The fabricated pair never actually received the relationship change.
    assert story.relationships.feelings("nobody_was_here", "also_not_here") == {}
    # Nobody who was never in a scene picked up a memory of one either (fake omniscience check).
    assert all(m.owner not in ("nobody_was_here", "also_not_here") for m in story.model.memories.memories)
    assert result.all_violations == []
