"""P-05: the rubric's labelled-set tooling (free parts only; nothing here calls Jev)."""
from __future__ import annotations

import json
import sys

import pytest

from backend.app.sim import rubric
from backend.app.sim.rubric import ItemScore
from scripts.eval import script_rubric_eval as ev

ITEMS = ev.SCENE_ITEMS


def labels(value=3, **overrides):
    return {**{i: value for i in ITEMS}, **overrides}


def scored(choice=3, **overrides):
    return rubric.aggregate("scene", [ItemScore(i, overrides.get(i, choice)) for i in ITEMS])


# --------------------------------------------------------------------------------------------- the data files
@pytest.mark.parametrize("name, size", [("dev", 40), ("holdout", 20)])
def test_the_candidate_files_are_well_formed(name, size):
    cases = ev.load(name)
    assert len(cases) == size and len({c["id"] for c in cases}) == size
    for case in cases:
        assert case["text"].strip() and case["source"].startswith("arena:") and case["setting"]
        assert case["labels"] is None or ev.labelled([case]) == [case], f"{case['id']}: labels must be complete 1-5"


def test_dev_and_holdout_share_no_scene():
    dev, holdout = ev.load("dev"), ev.load("holdout")
    assert not {c["id"] for c in dev} & {c["id"] for c in holdout}
    assert not {c["text"] for c in dev} & {c["text"] for c in holdout}


def test_the_anchor_sheet_lists_every_scene_item_with_five_anchors():
    sheet = ev.anchor_sheet()
    assert all(f"{item}  " in sheet for item in ITEMS)
    assert sum(1 for line in sheet.splitlines() if line.strip()[:2] in {"1 ", "2 ", "3 ", "4 ", "5 "}) == 5 * len(ITEMS)


# ----------------------------------------------------------------------------------------------- labels, verdict
def test_only_complete_labels_in_range_count():
    cases = [{"labels": labels()}, {"labels": None}, {"labels": labels(S3=6)}, {"labels": {"S1": 3}}, {}]
    assert ev.labelled(cases) == [cases[0]]


def test_the_human_verdict_uses_the_same_rule_as_the_rubric():
    assert ev.human_verdict(labels(5)) == "Recommend"
    assert ev.human_verdict(labels(4)) == "Recommend"              # mean 8, floor 8, plausibility 8
    assert ev.human_verdict(labels(4, S6=3)) == "Consider"         # plausibility 6
    assert ev.human_verdict(labels(1)) == "Pass"


# ---------------------------------------------------------------------------------------------------- agreement
def test_perfect_agreement_meets_the_bar():
    cases = [{"labels": labels(c)} for c in (2, 3, 4, 5)]
    agreement = ev.tally(cases, [scored(c) for c in (2, 3, 4, 5)])
    assert all(agreement.rate(agreement.exact, i) == 1.0 for i in ITEMS)
    assert agreement.verdict_rate == 1.0 and agreement.passes()


def test_being_two_points_off_on_an_item_misses_the_bar_even_if_the_rest_agree():
    cases = [{"labels": labels(3)} for _ in range(5)]
    agreement = ev.tally(cases, [scored(3, S4=5) for _ in range(5)])        # S4 is 2 points off everywhere
    assert agreement.rate(agreement.within_one, "S4") == 0.0 and agreement.rate(agreement.within_one, "S1") == 1.0
    assert not agreement.passes()


def test_one_point_off_counts_as_within_one_but_not_exact():
    agreement = ev.tally([{"labels": labels(3)}], [scored(4)])
    assert agreement.rate(agreement.exact, "S1") == 0.0 and agreement.rate(agreement.within_one, "S1") == 1.0


def test_unanswered_items_are_counted_and_an_unanswerable_item_fails_the_bar():
    cases = [{"labels": labels(3)} for _ in range(3)]
    results = [rubric.aggregate("scene", [ItemScore(i, None if i == "S2" else 3) for i in ITEMS]) for _ in range(3)]
    agreement = ev.tally(cases, results)
    assert agreement.unanswered == 3 and agreement.rate(agreement.within_one, "S2") is None
    assert agreement.verdict_rate is None and not agreement.passes()


def test_no_scenes_never_meets_the_bar():
    assert not ev.tally([], []).passes()


def test_the_report_names_items_below_the_bar(capsys):
    agreement = ev.tally([{"labels": labels(3)}], [scored(3, S4=5)])
    ev.report(agreement, "dev")
    out = capsys.readouterr().out
    assert "S4" in out and "<-- below bar" in out and "BAR: NOT MET" in out


# ------------------------------------------------------------------------------------------- building candidates
def _arena(tmp_path, runs=6, turns=3):
    for r in range(runs):
        arms = tmp_path / "arena_six_x" / "arms"
        arms.mkdir(parents=True, exist_ok=True)
        (arms / f"six.run{r}.json").write_text(json.dumps({"arm_id": f"six.run{r}", "turns": [
            {"index": t + 1, "player_message": f"hello {r}-{t}", "reply": f"Reply {r}-{t}. " + "x " * 300, "error": ""}
            for t in range(turns)] + [{"index": 99, "player_message": "short", "reply": "too short", "error": ""},
                                      {"index": 98, "player_message": "bad", "reply": "y " * 300, "error": "boom"}]}),
                                                  encoding="utf-8")
    return tmp_path


def test_candidates_are_deterministic_unlabelled_and_spread_across_runs(tmp_path):
    source = _arena(tmp_path)
    dev, holdout = ev.build_candidates(source, dev=5, holdout=3, seed=1)
    assert (dev, holdout) == ev.build_candidates(source, dev=5, holdout=3, seed=1)
    assert len(dev) == 5 and len(holdout) == 3 and all(c["labels"] is None for c in dev + holdout)
    ids = [c["id"] for c in dev + holdout]
    assert len(set(ids)) == 8 and not any(i.endswith((".t99", ".t98")) for i in ids)     # stubs and errors left out
    per_run = {}
    for c in dev + holdout:
        per_run[c["source"].split(":")[2]] = per_run.get(c["source"].split(":")[2], 0) + 1
    assert max(per_run.values()) <= 2


def test_too_few_transcripts_is_an_error_not_a_short_set(tmp_path):
    with pytest.raises(SystemExit, match="need 60"):
        ev.build_candidates(_arena(tmp_path, runs=2), dev=40, holdout=20)


def _cli(monkeypatch, tmp_path, *args):
    monkeypatch.setattr(ev, "DATA", tmp_path / "cases")
    monkeypatch.setattr(sys, "argv", ["script_rubric_eval", *args])
    return ev.main()


def test_build_candidates_refuses_to_overwrite_labels(monkeypatch, tmp_path):
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "dev.json").write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        _cli(monkeypatch, tmp_path, "--build-candidates", "--source", str(_arena(tmp_path / "arena", runs=40)))
    assert (cases / "dev.json").read_text(encoding="utf-8") == "[]"


def test_running_against_live_jev_refuses_when_nothing_is_labelled(monkeypatch, tmp_path):
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "dev.json").write_text(json.dumps([{"id": "a", "text": "t", "labels": None}]), encoding="utf-8")
    called = []
    monkeypatch.setattr(ev, "judge_cases", lambda *a, **k: called.append(1))
    with pytest.raises(SystemExit, match="no labelled scenes"):
        _cli(monkeypatch, tmp_path, "--run", "--set", "dev")
    assert not called                                    # nothing was spent


def test_status_counts_labelled_scenes(monkeypatch, tmp_path, capsys):
    cases = tmp_path / "cases"
    cases.mkdir()
    rows = [{"id": "a", "text": "t", "labels": labels()}, {"id": "b", "text": "t", "labels": None}]
    (cases / "dev.json").write_text(json.dumps(rows), encoding="utf-8")
    assert _cli(monkeypatch, tmp_path, "--status", "--set", "dev") == 0
    assert "1/2 scenes labelled" in capsys.readouterr().out
