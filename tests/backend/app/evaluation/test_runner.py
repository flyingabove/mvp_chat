"""Tests for ArenaRunner, pair building, store and player isolation
(JEV_GAME_ARENA_DESIGN.md §4, §5A, §6, §10)."""
import dataclasses

import pytest

from backend.app.evaluation.contracts import (
    BETA, PROD, ArmStatus, Budget, ExperimentManifest, PersonaSpec, ScenarioSpec,
)
from backend.app.evaluation.fakes import FakeTarget
from backend.app.evaluation.players import (
    PERSONAS, PlayerObservation, ScriptedPlayer, build_public_brief, build_player_prompt, clean_move,
)
from backend.app.evaluation.runner import ArenaRunner, build_pairs
from backend.app.evaluation.store import ArtifactStore, ManifestConflictError


def scenarios(turns=3):
    return [ScenarioSpec("s.a", "tiny", max_player_turns=turns), ScenarioSpec("s.b", "tiny", max_player_turns=turns)]


def personas():
    return [PersonaSpec("p1", "one"), PersonaSpec("p2", "two")]


async def make_runner(tmp_path, targets, budget=None):
    store = ArtifactStore(tmp_path, "exp")
    pinned = {side: await t.identify() for side, t in targets.items()}
    for t in targets.values():
        t.identify_calls = 0
    return store, ArenaRunner(experiment_id="exp", store=store, targets=targets, pinned=pinned,
                              player=ScriptedPlayer(["hello", "look around", "go to kitchen"]),
                              budget=budget or Budget(), concurrency=2)


def test_build_pairs_is_complete_balanced_and_deterministic():
    pairs = build_pairs(scenarios(), personas(), 2, seed=5)
    assert len(pairs) == 8 and len({p.pair_id for p in pairs}) == 8
    assert sum(p.first_side == BETA for p in pairs) == 4
    assert [p.pair_id for p in pairs] == [p.pair_id for p in build_pairs(scenarios(), personas(), 2, seed=5)]


@pytest.mark.asyncio
async def test_runner_plays_both_arms_and_persists_them(tmp_path):
    targets = {BETA: FakeTarget(BETA), PROD: FakeTarget(PROD)}
    store, r = await make_runner(tmp_path, targets)
    pairs = build_pairs(scenarios(), personas(), 1, seed=1)
    summary = await r.run(pairs)
    assert summary.statuses == {"complete": 8}
    arm = store.load_arm(pairs[0].arm_id(BETA))
    assert arm.status is ArmStatus.COMPLETE and len(arm.turns) == 3
    assert [t.player_message for t in arm.turns] == ["hello", "look around", "go to kitchen"]
    # every turn has a unique request id (server-side retry dedupe)
    ids = targets[BETA].request_ids
    assert len(ids) == len(set(ids)) == 12


@pytest.mark.asyncio
async def test_rerun_skips_finished_arms(tmp_path):
    targets = {BETA: FakeTarget(BETA), PROD: FakeTarget(PROD)}
    store, r = await make_runner(tmp_path, targets)
    pairs = build_pairs(scenarios(), personas()[:1], 1, seed=1)
    await r.run(pairs)
    sent = len(targets[BETA].request_ids)
    _, r2 = await make_runner(tmp_path, targets)
    s2 = await r2.run(pairs)
    assert s2.arms_skipped == 4 and len(targets[BETA].request_ids) == sent


@pytest.mark.asyncio
async def test_release_change_mid_arm_marks_drift_and_is_rerun(tmp_path):
    targets = {BETA: FakeTarget(BETA, drift_after_identify=1), PROD: FakeTarget(PROD)}
    store, r = await make_runner(tmp_path, targets)
    pairs = build_pairs(scenarios()[:1], personas()[:1], 1, seed=1)
    await r.run(pairs)
    assert store.load_arm(pairs[0].arm_id(BETA)).status is ArmStatus.DRIFT
    assert store.load_arm(pairs[0].arm_id(PROD)).status is ArmStatus.COMPLETE


@pytest.mark.asyncio
async def test_target_error_ends_arm_as_target_failure(tmp_path):
    targets = {BETA: FakeTarget(BETA, fail_at_turn=2), PROD: FakeTarget(PROD)}
    store, r = await make_runner(tmp_path, targets)
    pairs = build_pairs(scenarios()[:1], personas()[:1], 1, seed=1)
    await r.run(pairs)
    arm = store.load_arm(pairs[0].arm_id(BETA))
    assert arm.status is ArmStatus.TARGET_FAILURE and arm.turns[-1].error == "HTTP 500"


@pytest.mark.asyncio
async def test_engine_game_end_stops_arm_early_without_padding(tmp_path):
    targets = {BETA: FakeTarget(BETA, end_at_turn=2), PROD: FakeTarget(PROD)}
    store, r = await make_runner(tmp_path, targets)
    pairs = build_pairs(scenarios()[:1], personas()[:1], 1, seed=1)
    await r.run(pairs)
    arm = store.load_arm(pairs[0].arm_id(BETA))
    assert arm.status is ArmStatus.ENDED and len(arm.turns) == 2


@pytest.mark.asyncio
async def test_turn_budget_cancels_and_marks_partial(tmp_path):
    targets = {BETA: FakeTarget(BETA), PROD: FakeTarget(PROD)}
    store, r = await make_runner(tmp_path, targets, budget=Budget(max_game_turns=4))
    pairs = build_pairs(scenarios(), personas(), 1, seed=1)
    summary = await r.run(pairs)
    assert "ceiling" in summary.stopped_reason
    assert summary.game_turns <= 4 + 2 * 2                 # in-flight arms finish their current turn


@pytest.mark.asyncio
async def test_stop_file_cancels(tmp_path):
    targets = {BETA: FakeTarget(BETA), PROD: FakeTarget(PROD)}
    store, r = await make_runner(tmp_path, targets)
    (store.dir / "STOP").write_text("")
    summary = await r.run(build_pairs(scenarios(), personas(), 1, seed=1))
    assert summary.arms_run == 0 and "STOP" in summary.stopped_reason


def test_manifest_is_immutable_under_an_experiment_id(tmp_path):
    store = ArtifactStore(tmp_path, "exp")
    base = ExperimentManifest(
        experiment_id="exp", created_at="t", mode="as_deployed_product", targets={}, judge_model="jev-1.13.0",
        rubric_version="r", rubric_hash="h", evaluator_commit="c", player_model="m", player_prompt_version="v",
        knowledge_bundles={}, pairs=[], seed=1, window_turns=4, budget={}, notes=("a",))
    store.save_manifest(base)
    store.save_manifest(base)                               # identical: fine
    assert store.load_manifest().manifest_hash == base.manifest_hash
    with pytest.raises(ManifestConflictError):
        store.save_manifest(dataclasses.replace(base, seed=2))


# ---- player isolation ---------------------------------------------------------

def test_player_observation_has_no_field_for_hidden_information():
    names = {f.name for f in dataclasses.fields(PlayerObservation)}
    assert names == {"brief", "persona", "opening", "history", "turn", "max_turns"}


def test_public_brief_uses_only_public_story_fields():
    story = {"title": "T", "description": "D", "rules": {"player_role": "tenant"},
             "goal": {"win_text_rule": "win"}, "known_locations": [{"name": "Hall"}],
             "canonical_facts": [{"text": "SECRET"}], "characters": [{"name": "Hidden Person"}]}
    brief = build_public_brief(story)
    assert "SECRET" not in brief and "Hidden Person" not in brief
    assert "tenant" in brief and "Hall" in brief


def test_player_prompt_contains_only_own_history():
    obs = PlayerObservation("brief", PERSONAS["impatient_player"], "opening", [("hi", "hello")], 2, 8)
    prompt = build_player_prompt(obs)
    assert "ME: hi" in prompt and "GAME: hello" in prompt and "Action 2 of 8" in prompt


def test_clean_move_strips_role_labels_and_quotes():
    assert clean_move('"PLAYER: I stay here."') == "I stay here."
    assert clean_move("ME: go") == "go"


def test_five_design_personas_exist():
    assert set(PERSONAS) == {"exploratory_newcomer", "direct_investigator", "empathetic_builder",
                             "impatient_player", "boundary_tester"}
