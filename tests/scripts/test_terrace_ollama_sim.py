"""The offline Ollama simulation's pure helpers: environment routing and the gameplay metrics it reports."""
import types

import pytest

from scripts.terrace_ollama_sim import assert_local_only, ollama_env, repeated_sentence_share, summarise


def test_the_environment_routes_every_model_call_to_the_local_server_and_turns_jev_off():
    env = ollama_env("some-model")
    assert env["OPENAI_BASE_URL"] == env["STORY_MASTER_BASE_URL"] == "http://127.0.0.1:11434/v1"
    assert env["OPENAI_MODEL"] == env["STORY_MASTER_MODEL"] == "some-model"
    assert env["TYPESAFE_ENABLED"] == "false" and env["JEV_ENABLED_TASKS"] == ""
    assert "api.openai.com" not in " ".join(env.values()), "nothing in the overrides points at the cloud"
    assert env["LLM_PROVIDER"] == "ollama" and env["LLM_MODEL"] == "some-model", "the single provider switch is pinned"


def _settings(provider="ollama", openai="http://127.0.0.1:11434/v1", story="http://localhost:11434/v1"):
    return types.SimpleNamespace(LLM_PROVIDER=provider, OPENAI_BASE_URL=openai, STORY_MASTER_BASE_URL=story)


def test_the_simulation_refuses_to_run_unless_everything_is_local():
    assert_local_only(_settings())                                                  # all local: fine
    for bad in (_settings(provider="gemini"), _settings(openai="https://api.openai.com/v1"),
                _settings(story="https://generativelanguage.googleapis.com/v1beta/openai")):
        with pytest.raises(SystemExit):
            assert_local_only(bad)


def test_repeated_sentence_share_counts_only_long_sentences_seen_before():
    texts = ["I think we should go outside now. Short one.", "Arisa smiles. I think we should go outside now!"]
    assert repeated_sentence_share(texts) == 0.5, "one of two long sentences is a repeat"
    assert repeated_sentence_share(["Hi there.", "Hi there."]) == 0.0, "short lines are ignored"
    assert repeated_sentence_share([]) == 0.0


def _row(turn, standing, gain, day=0, minute=0, label="warm", **extra):
    base = {"turn": turn, "label": label, "latency_s": 20.0, "prompt_tokens": 7000, "game_minute": minute,
            "game_day": day, "standing": standing, "gain": gain, "tier": "strangers", "together": False,
            "target_spoke": True, "compete_beats": 0, "rivals_with_aims": 2, "reply_text": "A reply that is long enough.",
            "ending": None, "extractor_error": 0, "card": False, "tags": [], "cues": []}
    base.update(extra)
    return base


def test_summary_reports_pacing_progress_and_feedback():
    rows = [_row(1, 3.0, 3.0, minute=0, tags=["helpful"], cues=["warm"]),
            _row(2, 3.0, 0.0, minute=8, tags=["complimentary"], cues=["flat"]),
            _row(3, 3.0, 0.0, minute=16),
            _row(4, 4.5, 1.5, day=1, minute=600, tags=["helpful"], cues=["stale"])]
    out = summarise(rows)
    assert out["turns"] == 4 and out["game_days_touched"] == 2
    assert out["avg_game_minutes_per_turn"] == round((8 + 8 + 584) / 3, 1)
    assert out["zero_gain_share_of_talk_turns"] == 0.5
    assert out["gain_by_game_day"] == {"0": 3.0, "1": 1.5} and out["turns_by_game_day"] == {"0": 3, "1": 1}
    assert out["first_turn_with_no_gain_after_progress"] == 2
    assert out["turns_with_a_reaction_cue"] == 3 and out["cue_kinds"] == {"warm": 1, "cool": 0, "flat": 1, "stale": 1}
    assert out["turns_with_a_tag"] == 3 and out["standing_start"] == 3.0 and out["standing_end"] == 4.5
    assert summarise([]) == {}
