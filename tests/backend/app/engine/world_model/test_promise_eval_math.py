"""The promise-judge eval's own arithmetic and label files (no network): these DO run on deploy."""
import json
from collections import Counter

from scripts.eval import promise_judge_eval as evaluation


def test_the_gate_is_two_percent_and_a_wrongly_kept_exchange_always_fails_it():
    assert evaluation.GATE == 0.02
    ok = evaluation.Stats(total=200, done_total=100, done_missed=2, other_total=100)
    assert ok.miss_rate == 0.02 and ok.passed
    assert not evaluation.Stats(total=200, done_total=100, done_missed=3, other_total=100).passed
    assert not evaluation.Stats(total=200, done_total=100, other_total=100, other_kept=1).passed
    assert not evaluation.Stats(total=200, done_total=100, other_total=100, unreachable=1).passed


def test_wilson_interval_brackets_the_rate_and_narrows_with_more_cases():
    low, high = evaluation.wilson(2, 171)
    assert low < 2 / 171 < high
    small_low, small_high = evaluation.wilson(2, 20)
    assert (small_high - small_low) > (high - low)
    assert evaluation.wilson(0, 0) == (0.0, 1.0)
    assert evaluation.wilson(0, 96)[0] == 0.0


def test_labeled_sets_are_well_formed_and_big_enough_for_the_gate():
    items = evaluation.load("all")
    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids)), "case ids must be unique"
    labels = Counter(item["label"] for item in items)
    assert set(labels) == {"done", "pending", "cancelled"}
    assert labels["done"] >= 150, "too few kept-promise cases to measure a 2% miss rate"
    for item in items:
        assert {"id", "promiser", "promise", "prior_user", "prior_reply", "message", "label"} <= set(item)
        assert item["promiser"] in ("player", "npc") and item["message"].strip()


def test_every_dataset_file_the_eval_names_exists_and_parses():
    for name in ("dev", "holdout"):
        rows = evaluation.load(name)
        assert rows and all(isinstance(row, dict) for row in rows)
    assert len(evaluation.load("all")) == len(evaluation.load("dev")) + len(evaluation.load("holdout"))
    assert len(evaluation.load("dev", limit=5)) == 5
    json.dumps(evaluation.load("dev", limit=1))


def _fake_run(answers_by_call):
    calls = []

    async def fake(items, concurrency=2):
        calls.append(len(items))
        answers = answers_by_call[len(calls) - 1]
        return [evaluation.promise_judge.Ruling(f"m{i}", act, "done" if act == "kept" else None)
                for i, act in enumerate(answers)]
    return fake, calls


def test_calls_jev_never_answered_are_asked_again_and_only_those(monkeypatch):
    fake, calls = _fake_run([["kept", "skip", "kept", "skip"], ["kept", "skip"], ["kept"]])
    monkeypatch.setattr(evaluation, "run", fake)
    slept = []
    monkeypatch.setattr(evaluation.time, "sleep", slept.append)
    rulings = evaluation.judge_all([{}] * 4, pauses_s=(5.0, 35.0))
    assert [r.action for r in rulings] == ["kept"] * 4
    assert calls == [4, 2, 1] and slept == [5.0, 35.0]


def test_a_call_that_stays_unanswered_is_reported_as_unreachable_not_as_a_miss(monkeypatch):
    fake, calls = _fake_run([["skip"], ["skip"], ["skip"]])
    monkeypatch.setattr(evaluation, "run", fake)
    monkeypatch.setattr(evaluation.time, "sleep", lambda s: None)
    items = [{"id": "x", "label": "done", "promiser": "player", "promise": "p", "prior_user": "", "prior_reply": "", "message": "m"}]
    stats = evaluation.measure(items)
    assert stats.unreachable == 1 and stats.done_total == 0 and stats.done_missed == 0 and not stats.passed


def test_nothing_is_retried_when_every_call_was_answered(monkeypatch):
    fake, calls = _fake_run([["kept", "kept"]])
    monkeypatch.setattr(evaluation, "run", fake)
    monkeypatch.setattr(evaluation.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("no retry expected")))
    evaluation.judge_all([{}, {}])
    assert calls == [2]
