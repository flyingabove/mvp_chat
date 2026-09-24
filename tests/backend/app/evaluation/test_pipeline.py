"""Tests for backend/app/evaluation/pipeline.py: order-swap remapping,
position-bias handling and reliability policy (JEV_GAME_ARENA_DESIGN.md §7-8)."""
import pytest

from backend.app.evaluation.contracts import ArmStatus, Outcome, PairSpec, PersonaSpec, ScenarioSpec
from backend.app.evaluation.fakes import FakeJevClient, choice, make_arm, marker_policy, tiny_bundle
from backend.app.evaluation.judge import JevPairwiseJudge
from backend.app.evaluation.pipeline import JudgePipeline, judge_arms
from backend.app.evaluation.rubric import DEFAULT_RUBRIC
from backend.app.evaluation.store import ArtifactStore

REPLIES = ["Mina waves from the kitchen.", "Jun hands you the lease.", "Mina laughs.", "Jun shrugs."]


def judge(policy=None, **kw):
    return JevPairwiseJudge(FakeJevClient(policy=policy or marker_policy()), DEFAULT_RUBRIC, backoff_s=0, **kw)


def values(result):
    return {k: v["value"] for w in result.windows for k, v in w["dimensions"].items()}


@pytest.mark.asyncio
async def test_order_swap_remaps_to_the_better_release_beta():
    beta = make_arm("beta", REPLIES)
    prod = make_arm("prod", REPLIES[:1] + ["BAD reply"] + REPLIES[2:])
    res = await judge_arms(tiny_bundle(), beta, prod, judge(), DEFAULT_RUBRIC, 4)
    assert set(values(res).values()) == {1.0}
    assert len(res.calls) == 2                       # one window, both orders
    assert {c.orientation for c in res.calls} == {"beta_as_A", "prod_as_A"}


@pytest.mark.asyncio
async def test_order_swap_remaps_to_the_better_release_prod():
    beta = make_arm("beta", ["BAD reply"] + REPLIES[1:])
    prod = make_arm("prod", REPLIES)
    res = await judge_arms(tiny_bundle(), beta, prod, judge(), DEFAULT_RUBRIC, 4)
    assert set(values(res).values()) == {0.0}


@pytest.mark.asyncio
async def test_position_biased_judge_yields_unresolved_not_a_win():
    """A judge that always says 'A' disagrees with itself after the swap."""
    def always_a(decision, state):
        if decision.id.startswith("cmp_"):
            return choice("A", ["A", "B", "tie", "insufficient_evidence"])
        return marker_policy()(decision, state)

    res = await judge_arms(tiny_bundle(), make_arm("beta", REPLIES), make_arm("prod", REPLIES),
                           judge(always_a), DEFAULT_RUBRIC, 4)
    cells = [c for w in res.windows for c in w["dimensions"].values()]
    assert all(c["value"] is None and c["reason"] == "order_disagreement" for c in cells)


@pytest.mark.asyncio
async def test_identical_arms_tie():
    arm = make_arm("beta", REPLIES)
    res = await judge_arms(tiny_bundle(), arm, arm, judge(), DEFAULT_RUBRIC, 4)
    assert set(values(res).values()) == {0.5}


@pytest.mark.asyncio
async def test_insufficient_evidence_is_unresolved():
    def insufficient(decision, state):
        if decision.id.startswith("cmp_"):
            return choice("insufficient_evidence", ["A", "B", "tie", "insufficient_evidence"])
        return marker_policy()(decision, state)

    res = await judge_arms(tiny_bundle(), make_arm("beta", REPLIES), make_arm("prod", REPLIES),
                           judge(insufficient), DEFAULT_RUBRIC, 4)
    assert all(c["reason"] == "insufficient_evidence" for w in res.windows for c in w["dimensions"].values())


@pytest.mark.asyncio
async def test_windows_split_long_arms_and_weights_sum_to_rubric_total():
    long = REPLIES * 3                                # 12 turns -> 3 windows of 4
    res = await judge_arms(tiny_bundle(), make_arm("beta", long), make_arm("prod", long), judge(),
                           DEFAULT_RUBRIC, 4)
    assert len(res.windows) == 3 and len(res.calls) == 6
    assert sum(v.weight for v in res.votes) == pytest.approx(DEFAULT_RUBRIC.total_weight)


@pytest.mark.asyncio
async def test_critical_probe_confirmed_only_on_the_bad_side():
    res = await judge_arms(tiny_bundle(), make_arm("beta", REPLIES), make_arm("prod", ["BAD"] + REPLIES[1:]),
                           judge(), DEFAULT_RUBRIC, 4)
    leak = res.windows[0]["probes"]["secret_leak"]
    assert leak["prod"]["confirmed"] and not leak["beta"]["confirmed"]


@pytest.mark.asyncio
async def test_evidence_spans_are_remapped_to_releases():
    def pick_span(decision, state):
        if decision.id.startswith("ev_"):
            return choice("A1r", sorted(decision.allowed))
        return marker_policy()(decision, state)

    res = await judge_arms(tiny_bundle(), make_arm("beta", REPLIES), make_arm("prod", REPLIES),
                           judge(pick_span), DEFAULT_RUBRIC, 4)
    spans = res.windows[0]["dimensions"]["canon"]["evidence"]
    assert {(s["orientation"], s["release"], s["turn"], s["kind"]) for s in spans} == {
        ("beta_as_A", "beta", 1, "game"), ("prod_as_A", "prod", 1, "game")}


# ---- JudgePipeline reliability policy ----------------------------------------

def pair():
    return PairSpec("tiny.x.r0", ScenarioSpec("tiny.x", "tiny"), PersonaSpec("p", "d"), 0, 1, "beta")


def pipeline(tmp_path, j=None):
    store = ArtifactStore(tmp_path, "exp")
    return store, JudgePipeline(store=store, bundles={"tiny": tiny_bundle()}, judge=j or judge(),
                                rubric=DEFAULT_RUBRIC, window_turns=4)


@pytest.mark.asyncio
async def test_target_failure_on_one_side_is_a_loss_for_that_release(tmp_path):
    store, pipe = pipeline(tmp_path)
    p = pair()
    store.save_arm(make_arm("beta", REPLIES[:1], pair_id=p.pair_id, status=ArmStatus.TARGET_FAILURE))
    store.save_arm(make_arm("prod", REPLIES, pair_id=p.pair_id))
    result = await pipe.judge_pair(p)
    assert result["outcome"] == Outcome.PROD_WIN.value
    assert any(f["check_id"] == "target_failure" for f in result["checks"]["beta"])


@pytest.mark.asyncio
async def test_both_failing_is_both_failed_not_a_tie(tmp_path):
    store, pipe = pipeline(tmp_path)
    p = pair()
    for side in ("beta", "prod"):
        store.save_arm(make_arm(side, [], pair_id=p.pair_id, status=ArmStatus.TARGET_FAILURE))
    assert (await pipe.judge_pair(p))["outcome"] == Outcome.BOTH_FAILED.value


@pytest.mark.asyncio
async def test_drifted_arm_makes_pair_invalid(tmp_path):
    store, pipe = pipeline(tmp_path)
    p = pair()
    store.save_arm(make_arm("beta", REPLIES, pair_id=p.pair_id, status=ArmStatus.DRIFT))
    store.save_arm(make_arm("prod", REPLIES, pair_id=p.pair_id))
    assert (await pipe.judge_pair(p))["outcome"] == Outcome.INVALID.value


@pytest.mark.asyncio
async def test_judge_infrastructure_failure_is_unresolved_and_not_cached(tmp_path):
    store, pipe = pipeline(tmp_path, JevPairwiseJudge(FakeJevClient(fail_times=99), DEFAULT_RUBRIC,
                                                      backoff_s=0, max_attempts=1))
    p = pair()
    store.save_arm(make_arm("beta", REPLIES, pair_id=p.pair_id))
    store.save_arm(make_arm("prod", ["BAD"] + REPLIES[1:], pair_id=p.pair_id))
    result = await pipe.judge_pair(p)
    assert result["outcome"] == Outcome.UNRESOLVED.value
    assert store.load_judgment(p.pair_id) is None     # rerun will retry


@pytest.mark.asyncio
async def test_successful_judgment_is_cached(tmp_path):
    store, pipe = pipeline(tmp_path)
    p = pair()
    store.save_arm(make_arm("beta", REPLIES, pair_id=p.pair_id))
    store.save_arm(make_arm("prod", ["BAD"] + REPLIES[1:], pair_id=p.pair_id))
    first = await pipe.judge_pair(p)
    assert first["outcome"] == Outcome.BETA_WIN.value
    assert store.load_judgment(p.pair_id)["outcome"] == Outcome.BETA_WIN.value
