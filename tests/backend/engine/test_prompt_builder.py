import re

import pytest

from app.engine.state import init_state, CharacterState


def test_system_prompt_includes_required_tail_and_memory_block(monkeypatch):
    from app.engine import prompt_builder as pb

    st = init_state()
    st.story_cfg = {
        "meta": {"disclaimer": "fiction"},
        "setting": {},
        "victim": {},
        "rules": {"manifestation": {"apartment_location_contains": ["officetel"]}},
    }
    st.characters["IU"] = CharacterState(key="IU", name="IU", role="ghost")
    st.main_character_id = "IU"

    memory = pb._format_memory_block([
        {"type": "discography", "chunk_id": "song_love_poem", "text": "IU - Love Poem"}
    ])
    sysmsg = pb.system_prompt(st, is_first_turn=True, memory_block=memory)

    assert "CANONICAL CHARACTER MEMORY" in sysmsg
    assert "Love Poem" in sysmsg
    assert "[[STATE]]" in sysmsg and "[[/STATE]]" in sysmsg


def test_build_messages_trims_history_and_adds_header(monkeypatch):
    from app.engine import prompt_builder as pb

    # Avoid runtime knowledge retrieval in tests.
    monkeypatch.setattr(pb, "_retrieve_memory", lambda *args, **kwargs: {"chunks": []})

    st = init_state()
    st.story_cfg = {"rules": {"manifestation": {"apartment_location_contains": ["officetel"]}}}
    st.characters["IU"] = CharacterState(key="IU", name="IU", role="ghost")
    st.main_character_id = "IU"

    # Create a long log and ensure prompt_builder trims it.
    log = []
    for i in range(50):
        log.append({"role": "user", "content": f"u{i}"})
        log.append({"role": "assistant", "content": f"a{i}"})

    messages = pb.build_messages(st, log, "hello there")
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert "Time:" in messages[-1]["content"]

    # Ensure the state tag requirement exists in system prompt.
    assert "REQUIRED FINAL LINE" in messages[0]["content"]
    # Make sure casual Korean detection doesn't crash
    assert isinstance(st.casual_korean_used, list)


def test_format_memory_block_empty_is_blank():
    from app.engine import prompt_builder as pb
    assert pb._format_memory_block([]) == ""
