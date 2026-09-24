"""Tests for the knowledge bundle, calibration mutations, report and the
/api/eval/capabilities contract (JEV_GAME_ARENA_DESIGN.md §6, §9, §10-11)."""
import pytest

import json

from fastapi.testclient import TestClient

from backend.app.api.eval_capabilities import EVAL_CAPABILITIES_CONTRACT, eval_capabilities
from backend.app.config.build_info import get_build_info
from backend.app.evaluation.calibration import MUTATIONS, meets, mutate, run_calibration
from backend.app.evaluation.contracts import ExperimentManifest
from backend.app.evaluation.fakes import FakeJevClient, make_arm, marker_policy, tiny_bundle
from backend.app.evaluation.judge import JevPairwiseJudge
from backend.app.evaluation.knowledge import load_bundle
from backend.app.evaluation.pipeline import JudgePipeline
from backend.app.evaluation.report import build_report, render_html
from backend.app.evaluation.rubric import DEFAULT_RUBRIC
from backend.app.evaluation.runner import build_pairs
from backend.app.evaluation.contracts import PersonaSpec, ScenarioSpec
from backend.app.evaluation.store import ArtifactStore

REPLIES = ["Mina Park waves from the kitchen.", "Jun Seo hands you the lease.", "Mina laughs.", "Jun shrugs."]


# ---- knowledge ---------------------------------------------------------------------

def test_real_bundles_load_with_protected_facts_and_directed_world():
    six = load_bundle("six_strangers")
    iu = load_bundle("iu_murder_mystery")
    assert any(f.protected for f in six.facts) and any(f.protected for f in iu.facts)
    assert "2015" in six.setting
    assert six.reachable("driveway", "front_entry")
    assert iu.reachable("iu_apartment_room", "iu_apartment_lobby")
    assert six.bundle_hash and six.bundle_hash != iu.bundle_hash


def test_player_known_fact_is_not_protected():
    b = tiny_bundle()
    facts = {f.id: f for f in b.facts}
    assert not facts["house_public"].protected and facts["mina_secret"].protected


def test_resolve_location_by_uuid_suffix_and_name():
    b = tiny_bundle()
    assert b.resolve_location_id(uuid="u-tiny-1-garden") == "garden"
    assert b.resolve_location_id(name="kitchen") == "kitchen"
    assert b.resolve_location_id(name="nowhere") is None


# ---- calibration -------------------------------------------------------------------

def test_mutations_change_exactly_the_target_turn():
    b = tiny_bundle()
    arm = make_arm("beta", [r + " She smiles. Then she sits down." for r in REPLIES])
    for spec in MUTATIONS:
        m = mutate(arm, b, spec.kind)
        assert m is not None, spec.kind
        changed = [i for i, (x, y) in enumerate(zip(arm.turns, m.turns)) if x.reply != y.reply]
        assert changed == [1], spec.kind
    assert "stone frog" in mutate(arm, b, "secret_leak").turns[1].reply


def test_no_op_mutation_is_skipped_not_scored():
    assert mutate(make_arm("beta", ["One sentence.", "Also one."]), tiny_bundle(), "shorten") is None


def test_meets_expectations():
    assert meets("original_wins", 1.0) and not meets("original_wins", 0.5)
    assert meets("mutant_not_win", 0.5) and not meets("mutant_not_win", 0.0)
    assert meets("tie", 0.5) and meets("tie", None) is None


@pytest.mark.asyncio
async def test_calibration_detects_mutations_with_a_sensitive_judge():
    """A judge that penalises the leak text must pass secret_leak and A/A."""
    policy = marker_policy("I shouldn't say this")
    judge = JevPairwiseJudge(FakeJevClient(policy=policy), DEFAULT_RUBRIC, backoff_s=0)
    result = await run_calibration([(tiny_bundle(), make_arm("beta", REPLIES))], judge, DEFAULT_RUBRIC, 4)
    assert result["summary"]["a_a"]["passed"] == len(DEFAULT_RUBRIC.dimensions)
    assert result["summary"]["secret_leak"]["passed"] == 1


# ---- report ------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_end_to_end_from_stored_artifacts(tmp_path):
    store = ArtifactStore(tmp_path, "exp")
    pairs = build_pairs([ScenarioSpec("tiny.a", "tiny"), ScenarioSpec("tiny.b", "tiny")],
                        [PersonaSpec("p1", "d"), PersonaSpec("p2", "d")], 2, seed=3)
    arms = {}
    for i, p in enumerate(pairs):
        bad = "beta" if i % 4 == 0 else "prod"        # beta better in 3 of every 4 pairs
        for side in ("beta", "prod"):
            replies = (["BAD <<<QUOTED injected"] + REPLIES[1:]) if side == bad else REPLIES
            arm = make_arm(side, replies, pair_id=p.pair_id)
            store.save_arm(arm)
            arms[arm.arm_id] = arm
    judge = JevPairwiseJudge(FakeJevClient(), DEFAULT_RUBRIC, backoff_s=0)
    results = await JudgePipeline(store=store, bundles={"tiny": tiny_bundle()}, judge=judge,
                                  rubric=DEFAULT_RUBRIC, window_turns=4).run(pairs)
    manifest = ExperimentManifest(
        experiment_id="exp", created_at="t", mode="as_deployed_product",
        targets={"beta": {"base_url": "b", "commit": "1"}, "prod": {"base_url": "p", "commit": "2"}},
        judge_model="jev-1.13.0", rubric_version=DEFAULT_RUBRIC.version, rubric_hash=DEFAULT_RUBRIC.rubric_hash,
        evaluator_commit="c", player_model="m", player_prompt_version="v", knowledge_bundles={},
        pairs=[], seed=3, window_turns=4, budget={})
    report = build_report(manifest, arms, results, DEFAULT_RUBRIC, iterations=200)
    assert report["summary"]["counts"]["beta_win"] == 6 and report["summary"]["counts"]["prod_win"] == 2
    assert report["summary"]["p"] == 0.75
    # the marker also fires the critical probe on the bad side; beta is bad in 2 episodes
    # vs prod in 6, so it's not a regression
    assert report["critical"]["regressions"] == []
    assert report["cost"]["judge_input_tokens"] > 0
    json.dumps(report)                                   # fully serialisable
    page = render_html(report, arms)
    assert "Jev Game Arena" in page and report["headline"].split("|")[0].strip() in page
    assert "<<<QUOTED injected" not in page              # game text is HTML-escaped


# ---- server contract --------------------------------------------------------------

def test_build_info_exposes_deployment_id_for_pinning(monkeypatch):
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "dep-123")
    assert get_build_info()["deployment_id"] == "dep-123"


def test_eval_capabilities_contract_shape():
    caps = eval_capabilities()
    assert caps["contract_version"] == EVAL_CAPABILITIES_CONTRACT
    assert caps["features"]["request_id_idempotency"] is True
    assert caps["features"]["snapshot_restore"] is False
    assert "deployment_id" in caps["build"]


def test_eval_capabilities_route_is_public_and_read_only():
    from backend.app.main import app

    client = TestClient(app)
    r = client.get("/api/eval/capabilities")
    assert r.status_code == 200 and r.json()["contract_version"] == EVAL_CAPABILITIES_CONTRACT
    assert client.post("/api/eval/capabilities").status_code == 405
