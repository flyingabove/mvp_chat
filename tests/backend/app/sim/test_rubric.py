"""P-05: the Jev script rubric, with a fake Jev. Aggregation, the verdict rule, the advisory flag, failure handling."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.llm.decisions.types import Criticality, DecisionAnswer, FallbackReason, Provider
from backend.app.sim import rubric
from backend.app.sim.rubric import ItemScore


class FakeJev:
    """Answers each rubric question from `choices` (item id -> 1-5, or one number for all); records every batch."""

    def __init__(self, choices=3, unanswered=(), provider=Provider.JEV, fail=False):
        self.choices, self.unanswered, self.provider, self.fail = choices, set(unanswered), provider, fail
        self.batches = []

    async def resolve(self, batches, request):
        if self.fail:
            raise RuntimeError("jev is down")
        answers, reasons = {}, {}
        for batch in batches:
            self.batches.append(batch)
            for decision in batch.decisions:
                item_id = decision.id.removeprefix("rubric_")
                if item_id in self.unanswered:
                    answers[decision.id] = DecisionAnswer(decision.id, Provider.DEFAULT,
                                                          fallback_reason=FallbackReason.TIMEOUT)
                    reasons[decision.id] = FallbackReason.TIMEOUT
                    continue
                pick = self.choices.get(item_id, 3) if isinstance(self.choices, dict) else self.choices
                answers[decision.id] = DecisionAnswer(decision.id, self.provider, choice=str(pick), confidence=0.9)
        return SimpleNamespace(answers=answers, fallback_reasons=reasons)


# ----------------------------------------------------------------------------------------------- the items
def test_the_rubric_has_exactly_the_designed_items():
    assert [i.id for i in rubric.items_for("scene")] == ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]
    assert [i.id for i in rubric.items_for("day")] == ["E1", "E2", "E3", "E4", "E5", "E6"]
    assert [i.id for i in rubric.items_for("season")] == ["R1", "R2", "R3", "R4", "R5"]
    with pytest.raises(ValueError):
        rubric.items_for("episode")


def test_every_item_has_five_distinct_anchors_and_a_question():
    for item in rubric.ITEMS:
        assert item.question.endswith("?") and item.title
        assert len(item.anchors) == 5 and len(set(item.anchors)) == 5, item.id
        assert all(anchor.strip() for anchor in item.anchors)


def test_an_item_is_one_bounded_choice_with_the_anchors_as_options():
    decision = rubric.decision_for(rubric.BY_ID["S1"])
    assert decision.kind == "choice" and decision.task == rubric.TASK
    assert decision.allowed == frozenset("12345") and decision.none_option is None
    assert list(decision.criteria) == ["1", "2", "3", "4", "5"]
    assert decision.criteria["1"] == rubric.BY_ID["S1"].anchors[0]
    assert decision.criticality is Criticality.DEGRADABLE      # absence is a valid state: never a language model call


def test_answers_one_to_five_are_reported_as_two_to_ten():
    assert [ItemScore("S1", c).score for c in (1, 2, 3, 4, 5)] == [2, 4, 6, 8, 10]
    assert ItemScore("S1", None).score is None


# ------------------------------------------------------------------------------------------ the verdict rule
@pytest.mark.parametrize("mean, low, plausibility, expected", [
    (8.0, 6, 8, "Recommend"),            # exactly at every bar
    (9.5, 8, 10, "Recommend"),
    (8.0, 4, 8, "Consider"),             # an item below 5 blocks Recommend
    (8.4, 6, 6, "Consider"),             # plausibility below 8 blocks Recommend
    (8.4, 6, None, "Consider"),          # no plausibility figure: never Recommend
    (7.9, 6, 10, "Consider"),
    (6.0, 4, 6, "Consider"),
    (5.9, 4, 6, "Pass"),
    (2.0, 2, 2, "Pass"),
    (None, None, None, "Unscored"),
])
def test_the_verdict_rule(mean, low, plausibility, expected):
    assert rubric.verdict_for(mean, low, plausibility) == expected


def test_aggregate_takes_the_mean_floor_and_the_scenes_own_plausibility():
    items = [ItemScore(f"S{n}", c) for n, c in zip(range(1, 9), (4, 4, 4, 4, 4, 5, 4, 4))]
    result = rubric.aggregate("scene", items)
    assert result.mean == pytest.approx((8 * 7 + 10) / 8) and result.low == 8
    assert result.plausibility == 10 and result.verdict == "Recommend" and result.complete


def test_a_level_with_an_unanswered_item_is_unscored_never_partially_scored():
    items = [ItemScore("S1", 5), ItemScore("S2", None, reason="timeout")] + [ItemScore(f"S{n}", 5) for n in range(3, 9)]
    result = rubric.aggregate("scene", items)
    assert not result.complete and result.mean is None and result.verdict == "Unscored"


# --------------------------------------------------------------------------------------- judging with fake Jev
async def test_a_sample_scene_is_scored_offline_with_the_fake():
    sample = "Riko waits by the kettle. 'You said you would come,' she says. Paul looks at the door and says nothing."
    result = await rubric.judge_level("scene", rubric.scene_view(sample, "the kitchen"), FakeJev(4))
    assert result.complete and result.mean == 8.0 and result.low == 8
    assert result.plausibility == 8 and result.verdict == "Recommend"      # every bar is met exactly


async def test_one_batch_per_level_carries_the_view_and_every_question():
    jev = FakeJev(3)
    await rubric.judge_level("day", rubric.day_view(["a scene", "another scene"]), jev)
    (batch,) = jev.batches
    assert batch.name == "script_rubric_day" and len(batch.decisions) == 6
    assert "[Scene 2] another scene" in batch.state


async def test_questions_are_chunked_to_the_batch_limit(monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "JEV_MAX_QUESTIONS_PER_BATCH", 3)
    jev = FakeJev(3)
    result = await rubric.judge_level("scene", "x", jev)
    assert [len(b.decisions) for b in jev.batches] == [3, 3, 2] and result.complete


async def test_an_unreachable_jev_never_raises_and_leaves_the_level_unscored():
    result = await rubric.judge_level("scene", "x", FakeJev(fail=True))
    assert result.verdict == "Unscored" and all(i.choice is None for i in result.items)
    assert {i.reason for i in result.items} == {"http_error"}


async def test_an_item_jev_did_not_answer_is_unanswered_with_its_reason():
    result = await rubric.judge_level("scene", "x", FakeJev(5, unanswered={"S3"}))
    s3 = next(i for i in result.items if i.item_id == "S3")
    assert s3.choice is None and s3.reason == "timeout" and result.verdict == "Unscored"


async def test_an_answer_from_anything_but_jev_is_not_trusted():
    result = await rubric.judge_level("scene", "x", FakeJev(5, provider=Provider.LEGACY_LLM))
    assert result.verdict == "Unscored"


async def test_an_option_outside_one_to_five_is_not_a_score():
    result = await rubric.judge_level("scene", "x", FakeJev(7))
    assert result.verdict == "Unscored"


# ------------------------------------------------------------------------------------------ views and season
def test_views_clip_long_text_and_number_their_parts():
    long = "word " * 1000
    assert len(rubric.scene_view(long)) < rubric.SCENE_CLIP + 40
    day = rubric.day_view([long, "second"])
    assert day.startswith("One story day") and "[Scene 2] second" in day and len(day) < 2 * rubric.DAY_CLIP + 100
    assert "[Day 3]" in rubric.season_view(["a", "b", "c"])


async def test_a_season_is_scored_scene_by_scene_then_by_day_then_overall_and_is_advisory():
    days = [["scene one", "scene two"], ["scene three"]]
    report = await rubric.score_season(days, FakeJev(5))
    assert [len(d) for d in report.scenes] == [2, 1] and len(report.days) == 2
    assert report.season.level == "season" and report.season.verdict == "Recommend"
    assert report.days[0].plausibility == 10 and report.advisory is True
    text = report.render()
    assert text.startswith(rubric.ADVISORY_NOTE) and "season: Recommend" in text


async def test_a_day_takes_the_lowest_plausibility_of_its_scenes():
    class Uneven(FakeJev):
        n = 0

        async def resolve(self, batches, request):
            self.n += 1
            if batches[0].name == "script_rubric_scene":
                self.choices = {"S6": 5 if self.n == 1 else 2}      # the second scene is implausible
            else:
                self.choices = 5
            return await super().resolve(batches, request)

    report = await rubric.score_season([["fine", "implausible"]], Uneven(), concurrency=1)
    assert report.days[0].plausibility == 4
    assert report.days[0].verdict == "Consider"          # all-5 day, but plausibility 4 blocks Recommend


async def test_an_unscored_scene_stops_its_day_and_season_being_recommended():
    class FirstSceneDown(FakeJev):
        async def resolve(self, batches, request):
            self.unanswered = {"S6"} if batches[0].name == "script_rubric_scene" and not self.batches else set()
            return await super().resolve(batches, request)

    report = await rubric.score_season([["a", "b"]], FakeJev(5, unanswered=()), concurrency=1)
    assert report.days[0].verdict == "Recommend"
    broken = await rubric.score_season([["a", "b"]], FirstSceneDown(5), concurrency=1)
    assert broken.scenes[0][0].verdict == "Unscored"
    assert broken.days[0].plausibility is None and broken.days[0].verdict == "Consider"


def test_the_advisory_flag_follows_calibration(monkeypatch):
    assert rubric.CALIBRATED is False
    monkeypatch.setattr(rubric, "CALIBRATED", True)
    import asyncio
    report = asyncio.run(rubric.score_season([["x"]], FakeJev(3)))
    assert report.advisory is False and rubric.ADVISORY_NOTE not in report.render()
    assert report.to_dict()["note"] == ""
