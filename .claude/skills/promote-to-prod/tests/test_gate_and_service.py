"""Tests for the release gate, multi-judge reports and the shared
service.run_experiment path (play once, judge with every judge)."""
import json

import pytest

import arena.service as service
from arena.aggregate import release_gate
from arena.contracts import BETA, PROD
from arena.fakes import FakeJevClient, FakeTarget, marker_policy
from arena.judge import JevPairwiseJudge
from arena.players import ScriptedPlayer
from arena.rubric import DEFAULT_RUBRIC
from arena.service import ArenaConfig, JudgeSpec, ModelEndpoint, judge_specs
from arena.suite import PROFILES, profile_scenarios

GAMES = ["iu_murder_mystery", "six_strangers"]


# ---- gate --------------------------------------------------------------------

def test_gate_passes_when_each_game_is_won_under_at_least_one_judge():
    gate = release_gate({"jev": {GAMES[0]: 0.7, GAMES[1]: 0.3}, "llm": {GAMES[0]: 0.4, GAMES[1]: 0.6}}, GAMES)
    assert gate["passed"]
    assert gate["per_game"][GAMES[0]]["beta_wins_under"] == ["jev"]
    assert gate["per_game"][GAMES[1]]["beta_wins_under"] == ["llm"]


def test_gate_fails_when_a_game_is_below_prod_under_every_judge():
    gate = release_gate({"jev": {GAMES[0]: 0.9, GAMES[1]: 0.4}, "llm": {GAMES[0]: 0.9, GAMES[1]: None}}, GAMES)
    assert not gate["passed"]
    assert any("six_strangers" in r for r in gate["reasons"])


def test_a_tie_is_enough_not_every_change_touches_the_engine():
    """User decision 2026-09-24: ties count (Six Strangers was 5 ties under OpenAI)."""
    gate = release_gate({"jev": {GAMES[0]: 1.0, GAMES[1]: 0.0}, "llm": {GAMES[0]: 0.5, GAMES[1]: 0.5}}, GAMES)
    assert gate["passed"]
    assert gate["per_game"][GAMES[1]]["beta_wins_under"] == ["llm"]


def test_significant_regression_under_any_counted_judge_blocks():
    gate = release_gate({"jev": {g: 0.5 for g in GAMES}, "llm": {g: 0.6 for g in GAMES}}, GAMES,
                        significantly_worse={GAMES[1]: ["jev"]})
    assert not gate["passed"]
    assert gate["per_game"][GAMES[1]]["significantly_worse_under"] == ["jev"]


def test_gate_blocks_on_critical_regression_even_when_all_games_won():
    gate = release_gate({"jev": {g: 0.9 for g in GAMES}}, GAMES, ["[jev] Unearned secret leak"])
    assert not gate["passed"]


def test_gate_with_no_games_fails_closed():
    assert not release_gate({"jev": {}}, [])["passed"]


# ---- profiles / specs ----------------------------------------------------------

def test_profiles_bound_api_usage():
    assert len(profile_scenarios("smoke")) == 2 and PROFILES["smoke"]["turns"] == 10
    gate_pairs = len(profile_scenarios("gate")) * len(PROFILES["gate"]["personas"]) * PROFILES["gate"]["replicates"]
    assert gate_pairs == 12


def test_llm_judge_uses_one_window_per_episode_to_limit_calls():
    llm = ModelEndpoint("http://127.0.0.1:11434/v1", "ollama", "llama3.1:8b")
    specs = {s.name: s for s in judge_specs(["jev", "llm"], turns=6, llm=llm, jev_api_key="k")}
    assert specs["llm"].window_turns == 6 and specs["jev"].window_turns == 4
    assert specs["jev"].namespace == "" and specs["llm"].namespace == "llm"
    with pytest.raises(ValueError):
        judge_specs(["llm"], turns=6, llm=None)


# ---- end-to-end service with fakes --------------------------------------------

@pytest.mark.asyncio
async def test_run_experiment_plays_once_and_judges_with_every_judge(tmp_path, monkeypatch):
    """Both releases give identical fake replies, so every judge sees ties,
    and ties pass the gate (a release that changes nothing is not blocked)."""
    targets = {BETA: FakeTarget(BETA), PROD: FakeTarget(PROD)}
    monkeypatch.setattr(service, "targets_for", lambda cfg, client: targets)
    monkeypatch.setattr(service, "LLMPlayer", lambda client, **kw: ScriptedPlayer(["hi", "look", "ok"]))

    calls = {"jev": 0, "llm": 0}

    def fake_make_judge(spec, client):
        calls[spec.name] += 1
        return JevPairwiseJudge(FakeJevClient(policy=marker_policy("NEVER-MATCHES")), DEFAULT_RUBRIC,
                                model="jev-1.13.0", backoff_s=0)

    monkeypatch.setattr(service, "make_judge", fake_make_judge)
    llm = ModelEndpoint("http://127.0.0.1:11434/v1", "ollama", "jev-1.13.0")
    cfg = ArenaConfig(experiment_id="exp", root=tmp_path, beta_url="fake://b", prod_url="fake://p",
                      player=llm, judges=judge_specs(["jev", "llm"], turns=3, llm=llm, jev_api_key="k"),
                      profile="smoke")
    arena = await service.run_experiment(cfg, lambda m: None)
    store = cfg.store
    assert calls == {"jev": 1, "llm": 1}
    # games played exactly once: 2 smoke pairs x 10 turns per arm
    assert len(targets[BETA].request_ids) == 20 and len(targets[PROD].request_ids) == 20
    # judgments stored per judge namespace
    assert len(list((store.dir / "judgments").glob("*.json"))) == 2
    assert len(list((store.dir / "judgments" / "llm").glob("*.json"))) == 2
    assert set(arena["judges"]) == {"jev", "llm"}
    gate = json.loads((store.dir / "gate.json").read_text())
    assert gate == arena["gate"] and set(gate["per_game"]) == set(GAMES)
    assert gate["passed"] and all(g["beta_wins_under"] == ["jev", "llm"] for g in gate["per_game"].values())
    html = (store.dir / "report.html").read_text(encoding="utf-8")
    assert "Release gate" in html and "Judge: llm" in html
    assert (store.dir / "report_fragment.html").read_text(encoding="utf-8").startswith("<title>")


# ---- three evaluators, cheapest first ----------------------------------------

def test_ollama_judge_spec_is_a_one_window_llm_judge():
    ollama = ModelEndpoint("http://127.0.0.1:11434/v1", "ollama", "llama3.1-8b-ctx16k")
    (spec,) = judge_specs(["ollama"], turns=6, llm=None, ollama=ollama)
    assert (spec.name, spec.kind, spec.window_turns, spec.namespace) == ("ollama", "llm", 6, "ollama")
    with pytest.raises(ValueError):
        judge_specs(["ollama"], turns=6, llm=None)


def _fake_report(p_by_game, beta_fail=0, prod_fail=0, beta_err=0, prod_err=0, checks=None):
    return {
        "strata": {g: {"p": p} for g, p in p_by_game.items()},
        "critical": {"regressions": []},
        "reliability": {BETA: {"statuses": {"complete": 2, "target_failure": beta_fail}, "turn_errors": beta_err},
                        PROD: {"statuses": {"complete": 2, "target_failure": prod_fail}, "turn_errors": prod_err}},
        "checks": checks or {},
        "headline": "h",
    }


def _arena_with(monkeypatch, reports, gate_judges):
    """build_arena_report over fake per-judge reports (keyed by each judge's
    judgments list), with judgments that name both games."""
    import arena.report as report

    judgments = {name: [{"story_id": g} for g in GAMES] for name in reports}
    by_list = {id(js): reports[name] for name, js in judgments.items()}
    monkeypatch.setattr(report, "build_report", lambda manifest, arms, js, rubric, **kw: by_list[id(js)])
    manifest = type("M", (), {"experiment_id": "x"})()
    return report.build_arena_report(manifest, {}, judgments, DEFAULT_RUBRIC, gate_judges=gate_judges)


def test_gate_counts_only_gate_judges_and_reports_ollama_as_advisory(monkeypatch):
    arena = _arena_with(monkeypatch, {
        "jev": _fake_report({GAMES[0]: 0.7, GAMES[1]: 0.3}),
        "llm": _fake_report({GAMES[0]: 0.4, GAMES[1]: 0.4}),
        "ollama": _fake_report({GAMES[0]: 0.9, GAMES[1]: 0.9}),
    }, ("jev", "llm"))
    gate = arena["gate"]
    # Six Strangers is only "won" under the advisory ollama judge -> gate fails
    assert not gate["passed"] and gate["advisory_judges"] == ["ollama"]
    assert gate["judges_counted"] == ["jev", "llm"]
    assert gate["per_game"][GAMES[0]]["beta_wins_under"] == ["jev"]


def test_gate_falls_back_to_the_judges_that_ran(monkeypatch):
    """Offline runs have only the ollama judge; it then decides the gate."""
    arena = _arena_with(monkeypatch, {"ollama": _fake_report({GAMES[0]: 0.6, GAMES[1]: 0.6})}, ("jev", "llm"))
    assert arena["gate"]["judges_counted"] == ["ollama"] and arena["gate"]["passed"]


def test_precheck_verdict_is_about_reliability_not_local_quality():
    from arena.report import precheck_verdict

    ok = {"judges": {"ollama": _fake_report({GAMES[0]: 0.0, GAMES[1]: 0.0})}}
    assert precheck_verdict(ok)["passed"]                    # losing on quality alone never fails it
    broken = {"judges": {"ollama": _fake_report({GAMES[0]: 1.0}, beta_fail=1, beta_err=2,
                                                checks={"route_legality (major)": {BETA: 2, PROD: 0}})}}
    verdict = precheck_verdict(broken)
    assert not verdict["passed"] and len(verdict["reasons"]) == 3


def test_one_resolved_loss_is_not_called_significant(monkeypatch):
    """Real case 2026-09-24: Jev resolved a single Six Strangers episode (a prod
    win) -> bootstrap interval -inf..-inf; that must not block the gate."""
    single_loss = _fake_report({GAMES[0]: 1.0, GAMES[1]: 0.0})
    single_loss["strata"][GAMES[1]].update(counts={"beta_win": 0, "prod_win": 1, "tie": 0}, elo_interval=["-inf", "-inf"])
    ties = _fake_report({GAMES[0]: 0.5, GAMES[1]: 0.5})
    arena = _arena_with(monkeypatch, {"jev": single_loss, "llm": ties}, ("jev", "llm"))
    assert arena["gate"]["passed"]
    assert arena["gate"]["per_game"][GAMES[1]]["significantly_worse_under"] == []

    many_losses = _fake_report({GAMES[0]: 1.0, GAMES[1]: 0.0})
    many_losses["strata"][GAMES[1]].update(counts={"beta_win": 0, "prod_win": 6, "tie": 0}, elo_interval=["-inf", -240.0])
    arena = _arena_with(monkeypatch, {"jev": many_losses, "llm": ties}, ("jev", "llm"))
    assert not arena["gate"]["passed"]


def test_every_profile_plays_at_least_ten_turns():
    """User decision 2026-09-24: games must be at least 10 player turns."""
    from arena.suite import MIN_TURNS

    assert MIN_TURNS == 10
    assert all(spec["turns"] >= MIN_TURNS for spec in PROFILES.values())
    assert all(s.max_player_turns >= MIN_TURNS for s in profile_scenarios("gate"))


def test_cli_rejects_games_shorter_than_ten_turns():
    from arena.cli import main

    with pytest.raises(SystemExit, match="at least 10"):
        main(["all", "--turns", "6"])


# --- LLM arena runs are disabled by default (owner decision 2026-09-25) ---

@pytest.mark.parametrize("command", ["all", "run", "judge", "calibrate", "local", "precheck", "tiered"])
def test_llm_arena_commands_are_disabled_without_the_flag(command, monkeypatch):
    from arena.cli import main

    monkeypatch.delenv("ARENA_LLM_ENABLED", raising=False)
    with pytest.raises(SystemExit, match="disabled"):
        main([command])


def test_the_flag_must_be_explicitly_truthy(monkeypatch):
    from arena.cli import arena_llm_enabled

    for value, expected in (("1", True), ("true", True), ("0", False), ("", False), ("nope", False)):
        monkeypatch.setenv("ARENA_LLM_ENABLED", value)
        assert arena_llm_enabled() is expected


def test_release_helpers_stay_available_without_the_flag(monkeypatch):
    from arena.cli import LLM_COMMANDS

    monkeypatch.delenv("ARENA_LLM_ENABLED", raising=False)
    assert not {"wait-deploy", "smoke", "report"} & LLM_COMMANDS
