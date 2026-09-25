"""Tests for ArenaRunner, pair building, store and player isolation
(JEV_GAME_ARENA_DESIGN.md §4, §5A, §6, §10)."""
import dataclasses

import pytest

from arena.contracts import (
    BETA, PROD, ArmStatus, Budget, ExperimentManifest, PersonaSpec, ScenarioSpec,
)
from arena.fakes import FakeTarget
from arena.players import (
    PERSONAS, PlayerObservation, ScriptedPlayer, build_public_brief, build_player_prompt, clean_move,
)
from arena.runner import ArenaRunner, build_pairs
from arena.store import ArtifactStore, ManifestConflictError


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


# ---- provider-limit resilience (pilot 2026-09-23 hit shared OpenAI 429s) -------

import httpx

from arena.players import LLMPlayer
from arena.targets import ArmSession, HostedTargetAdapter, is_transient


def scripted_transport(responses, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        status, body = responses.pop(0)
        return httpx.Response(status, json=body)
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_transient_game_error_is_retried_with_the_same_request_id():
    seen = []
    transport = scripted_transport([
        (200, {"error": "The story master is unavailable right now. Please try that again in a moment."}),
        (200, {"reply": "Mina waves.", "segments": []}),
    ], seen)
    async with httpx.AsyncClient(transport=transport) as client:
        target = HostedTargetAdapter("beta", "https://x", client, backoff_s=0)
        res = await target.send(ArmSession("s", "g"), "hi", "req-1")
    assert res.reply == "Mina waves." and not res.error
    assert [r.read() for r in seen][0] == seen[1].read()      # identical resend (same request_id)
    assert b'"request_id":"req-1"' in seen[1].read().replace(b" ", b"")


@pytest.mark.asyncio
async def test_non_transient_game_error_is_not_retried():
    seen = []
    transport = scripted_transport([(200, {"error": "story not found: nope"})], seen)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await HostedTargetAdapter("beta", "https://x", client, backoff_s=0).send(ArmSession("s", "g"), "hi", "r")
    assert res.error.startswith("story not found") and len(seen) == 1


@pytest.mark.asyncio
async def test_transient_error_without_request_id_is_never_resent():
    """newgame has no request_id, so a resend could not be deduplicated."""
    seen = []
    transport = scripted_transport([(200, {"error": "upstream HTTP 429: rate limit"})], seen)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await HostedTargetAdapter("beta", "https://x", client, backoff_s=0).post_chat(ArmSession("s", "g"), "__cmd_newgame__:x")
    assert res.error and len(seen) == 1


def test_transient_classifier():
    assert is_transient("upstream HTTP 429: Rate limit reached for gpt-4o-mini")
    assert is_transient("The story master is unavailable right now. Please try that again in a moment.")
    assert is_transient("The scene response was incomplete. Please try again.")
    assert not is_transient("story not found: x")


@pytest.mark.asyncio
async def test_player_retries_provider_rate_limit_then_succeeds():
    seen = []
    transport = scripted_transport([
        (429, {"error": {"message": "Rate limit"}}),
        (200, {"choices": [{"message": {"content": "I stay here."}}], "usage": {"total_tokens": 12}}),
    ], seen)
    async with httpx.AsyncClient(transport=transport) as client:
        player = LLMPlayer(client, api_key="k", backoff_s=0)
        obs = PlayerObservation("brief", PERSONAS["boundary_tester"], "opening", [], 1, 8)
        move = await player.next_move(obs, seed=1)
    assert move.message == "I stay here." and not move.error and len(seen) == 2


@pytest.mark.asyncio
async def test_player_gives_up_after_bounded_attempts():
    seen = []
    transport = scripted_transport([(429, {})] * 3, seen)
    async with httpx.AsyncClient(transport=transport) as client:
        player = LLMPlayer(client, api_key="k", backoff_s=0, max_attempts=3)
        move = await player.next_move(PlayerObservation("b", PERSONAS["impatient_player"], "o", [], 1, 8), seed=1)
    assert move.error.startswith("gave up after 3") and len(seen) == 3


@pytest.mark.asyncio
async def test_player_brief_includes_own_character_name(tmp_path):
    """A human knows the name they typed at game start; the arena player must
    too (the pilot's player wrote '[Your Name]')."""
    seen = []

    class Recording(ScriptedPlayer):
        async def next_move(self, obs, *, seed):
            seen.append(obs.brief)
            return await super().next_move(obs, seed=seed)

    targets = {BETA: FakeTarget(BETA), PROD: FakeTarget(PROD)}
    store, r = await make_runner(tmp_path, targets)
    r.player = Recording(["hi"])
    await r.run(build_pairs([ScenarioSpec("s.a", "tiny", player_name="Jamie", max_player_turns=1)],
                            personas()[:1], 1, seed=1))
    assert seen and all("Your name: Jamie" in b for b in seen)
