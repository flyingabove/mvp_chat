"""P-06: the pilot-season script, offline (scripted writer and scripted Jev; nothing here touches a network)."""
import json
from types import SimpleNamespace

import pytest

from backend.app.llm.decisions.types import DecisionAnswer, Provider
from backend.app.sim.llm_writer import LLMWriter
from scripts import run_season


class FakeJev:
    """Answers every rubric question with 4 and records the batches."""

    def __init__(self):
        self.batches = []

    async def resolve(self, batches, request):
        answers = {}
        for batch in batches:
            self.batches.append(batch)
            answers.update({d.id: DecisionAnswer(d.id, Provider.JEV, choice="4", confidence=0.9) for d in batch.decisions})
        return SimpleNamespace(answers=answers, fallback_reasons={})


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _scripted_writer(setup_unused_loop, setup, cap):
    def chat(system, user, temperature, max_tokens):
        if system.startswith("You write"):
            return "They talked about the dishes for a while."
        return '{"summary": "They talked about the dishes.", "relationship_deltas": []}'
    return LLMWriter(chat, setup, cap)


def test_the_plan_is_two_calls_per_scene_and_printed_before_anything_starts(tmp_path, capsys):
    code = run_season.main(["--fake", "--no-score", "--days", "1", "--scenes-per-day", "2", "--out", str(tmp_path)])
    first = capsys.readouterr().out.splitlines()[0]
    assert code == 0 and "HARD CAP 20 model calls, this run needs up to 4" in first and "provider fake" in first
    rows = _rows(tmp_path / "season.jsonl")
    assert rows[-1] == {"type": "rubric", "report": None} and rows[0]["calls_used"] == 2     # not scored: said so, no zero


def test_a_run_over_the_cap_is_refused_before_it_starts(tmp_path, capsys):
    code = run_season.main(["--fake", "--days", "5", "--scenes-per-day", "3", "--out", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 2 and "needs up to 30 model calls, over the cap of 20" in captured.err
    assert captured.out == "" and not list(tmp_path.iterdir())


def test_raising_the_cap_on_purpose_allows_the_longer_run(tmp_path, capsys):
    code = run_season.main(["--fake", "--no-score", "--days", "4", "--scenes-per-day", "3", "--call-cap", "30",
                            "--out", str(tmp_path)])
    assert code == 0 and "wrote 12 scene(s) over 4 day(s)" in capsys.readouterr().out


def test_openai_is_refused_without_the_flag_including_the_silent_fallback():
    args = run_season.parse_args(["--provider", "openai"])
    assert "costs money" in run_season.refusal(args, "openai")
    assert run_season.refusal(run_season.parse_args(["--provider", "openai", "--allow-openai"]), "openai") is None
    assert run_season.refusal(args, "gemini") is None


def test_gemini_with_no_key_that_falls_back_to_openai_is_what_gets_refused(monkeypatch):
    from backend.app.llm import chat
    monkeypatch.setattr(chat, "get_gemini_api_key", lambda: "")
    monkeypatch.setattr(chat, "get_openai_api_key", lambda: "sk-test")
    monkeypatch.setitem(chat._PROVIDERS, "gemini", chat._Spec(chat.GEMINI_BASE_URL, chat.GEMINI_DEFAULT_MODEL, lambda: ""))
    monkeypatch.setitem(chat._PROVIDERS, "openai", chat._Spec(chat.OPENAI_BASE_URL, chat.OPENAI_DEFAULT_MODEL, lambda: "sk-test"))
    args = run_season.parse_args([])
    provider, _ = run_season.resolve_provider(args)
    assert provider == "openai" and "costs money" in run_season.refusal(args, provider)


def test_bad_sizes_are_refused():
    assert "at least 1" in run_season.refusal(run_season.parse_args(["--days", "0"]), "gemini")


def test_a_scored_run_writes_the_scene_prose_the_state_and_the_rubric(tmp_path, capsys):
    code = run_season.main(["--days", "2", "--scenes-per-day", "1", "--provider", "gemini", "--seed", "t1",
                            "--out", str(tmp_path)], writer_factory=_scripted_writer, resolver=FakeJev())
    out = capsys.readouterr().out
    rows = _rows(tmp_path / "season.jsonl")
    kinds = [r["type"] for r in rows]
    assert code == 0 and kinds == ["run", "scene", "day", "scene", "day", "state", "rubric"]
    run, scene = rows[0], rows[1]
    assert run["provider"] == "gemini" and run["calls_used"] == 4 and run["call_cap"] == 20 and run["seed"] == "t1"
    assert scene["text"] == "They talked about the dishes for a while." and scene["clock"].startswith("Wednesday")
    assert scene["a"] in run["cast"] and scene["rejections"] == []
    report = rows[-1]["report"]
    assert len(report["scenes"]) == 2 and report["season"]["verdict"] in ("Pass", "Consider", "Recommend")
    assert "season:" in out and "ADVISORY" not in out


def test_a_failed_model_call_is_reported_as_a_failure_and_scores_nothing(tmp_path, capsys):
    def broken(loop, setup, cap):
        def chat(system, user, temperature, max_tokens):
            raise RuntimeError("provider down")
        return LLMWriter(chat, setup, cap)

    code = run_season.main(["--days", "1", "--provider", "gemini", "--out", str(tmp_path)], writer_factory=broken,
                           resolver=FakeJev())
    captured = capsys.readouterr()
    assert code == 1 and "season FAILED" in captured.err and "provider down" in captured.err
    assert "wrote" not in captured.out and not list(tmp_path.iterdir())


def test_hitting_the_writer_call_cap_mid_run_is_a_reported_failure(tmp_path, capsys):
    def tight(loop, setup, cap):
        return _scripted_writer(loop, setup, 3)           # needs 4 for two scenes

    code = run_season.main(["--days", "1", "--scenes-per-day", "2", "--provider", "gemini", "--out", str(tmp_path)],
                           writer_factory=tight, resolver=FakeJev())
    assert code == 1 and "call cap of 3" in capsys.readouterr().err

