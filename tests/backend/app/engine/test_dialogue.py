import json
import pytest
from pathlib import Path
from types import SimpleNamespace

from backend.app.engine.dialogue import dialogue_prompt, dialogue_response_format, present_dialogue, encode_dialogue, decode_dialogue_response, drop_player_echo, clean_spoken_text
from backend.app.engine.state import Character, extract_state_tag


def state():
    return SimpleNamespace(characters={
        "mizuki": Character(key="mizuki", name="Mizuki Shida"),
        "iu": Character(key="iu", name="IU"),
    })


def test_mixed_speakers_preserve_order_and_plain_memory_text():
    text = 'A door opens. [SPEAKER:mizuki]Hello, IU.[/SPEAKER] She smiles. [SPEAKER:iu]Hi.[/SPEAKER]'
    clean, blocks = present_dialogue(text, state())
    assert clean == 'A door opens. Hello, IU. She smiles. Hi.'
    assert [b['kind'] for b in blocks] == ['narration', 'dialogue', 'narration', 'dialogue']
    assert blocks[1]['speaker_name'] == 'Mizuki Shida'
    assert blocks[1]['portrait_url'].endswith('Mizuki_Shida.png')
    assert blocks[3]['speaker_id'] == 'iu'
    assert present_dialogue(encode_dialogue(blocks), state())[1] == blocks


def test_unknown_and_malformed_tags_never_impersonate_main_character():
    clean, blocks = present_dialogue('[SPEAKER:invented]Who? [SPEAKER:iu]Me.', state())
    assert clean == 'Who? Me.'
    assert blocks[0]['speaker_id'] is None
    assert blocks[0]['speaker_name'] == 'Unknown voice'
    assert blocks[1]['speaker_id'] == 'iu'


def test_legacy_prose_is_not_guessed_from_mentioned_names():
    text = 'IU looks at Mizuki. "Hello," someone says.'
    assert present_dialogue(text, state()) == (text, [{'kind': 'narration', 'text': text}])


def test_portraits_only_accept_local_authored_assets():
    s = state()
    s.characters['iu'].meta['portrait_url'] = 'https://untrusted.example/a.png'
    assert present_dialogue('[SPEAKER:iu]Hi[/SPEAKER]', s)[1][0]['portrait_url'].startswith('/img/')
    s.characters['iu'].meta['portrait_url'] = '/img/characters/custom.png'
    assert present_dialogue('[SPEAKER:iu]Hi[/SPEAKER]', s)[1][0]['portrait_url'].endswith('custom.png')


def test_contract_applies_to_each_story_and_authored_openings_are_segmented():
    root = Path(__file__).resolve().parents[4] / 'backend/app/stories'
    for path in root.glob('*/*_story.json'):
        story = json.loads(path.read_text(encoding='utf-8'))
        s = SimpleNamespace(characters={c['key']: Character.from_dict(c) for c in story['characters']})
        prompt = dialogue_prompt(s)
        assert all(key in prompt for key in s.characters)
        clean, blocks = present_dialogue(story['opening']['text'], s)
        assert '[SPEAKER:' not in clean
        assert blocks
        if not story['opening'].get('variants'):
            assert any(b['kind'] == 'dialogue' for b in blocks)


def test_segments_survive_history_pagination(tmp_path, monkeypatch):
    from backend.app.db import repos
    monkeypatch.setattr(repos, '_jsonl_path', lambda *args: tmp_path / 'history.jsonl')
    clean, segments = present_dialogue('[SPEAKER:iu]Hello[/SPEAKER]', state())
    repos.ConversationRepo._append('u', 's', 'Hi', clean, 1, segments=segments)
    entries = repos.ConversationRepo._load_page('u', 's', 9999, 20)
    assert entries[1]['segments'] == segments
    assert entries[1]['content'] == 'Hello'


def test_structured_state_never_leaks_into_scene_and_consecutive_speech_is_grouped():
    from backend.app.engine.state import extract_state_tag
    raw = json.dumps({'segments': [
        {'kind': 'dialogue', 'speaker_id': 'iu', 'text': 'Hello.'},
        {'kind': 'dialogue', 'speaker_id': 'iu', 'text': 'Welcome.'},
        {'kind': 'narration', 'speaker_id': None, 'text': '[[STATE]]'},
    ], 'state': {'emotion': 'happy', 'rel_delta': 1}})
    prose, tag = extract_state_tag(decode_dialogue_response(raw))
    clean, blocks = present_dialogue(prose, state())
    assert tag == {'emotion': 'happy', 'rel_delta': 1}
    assert 'STATE' not in clean
    assert len(blocks) == 1
    assert blocks[0]['text'] == 'Hello.\n\nWelcome.'


def test_truncated_json_cannot_be_displayed_as_story_prose():
    with pytest.raises(ValueError, match='Incomplete structured scene'):
        decode_dialogue_response('{"segments":[{"kind":"dialogue","text":"Cut short')


def test_explicit_character_prefix_inside_narration_is_promoted_to_dialogue():
    raw = json.dumps({'segments': [{
        'kind': 'narration', 'speaker_id': None,
        'text': 'She smiles.\n\nMizuki Shida: “I make coffee.”\n\nThe kettle clicks.'
    }], 'state': {'emotion': 'warm', 'rel_delta': 0}})
    prose, _ = extract_state_tag(decode_dialogue_response(raw, state()))
    clean, blocks = present_dialogue(prose, state())
    assert clean == 'She smiles.\n\n“I make coffee.”\n\nThe kettle clicks.'
    assert [block['kind'] for block in blocks] == ['narration', 'dialogue', 'narration']
    assert blocks[1]['speaker_id'] == 'mizuki'
    assert blocks[1]['speaker_name'] == 'Mizuki Shida'


def test_bare_quotes_in_narration_are_not_guessed():
    raw = json.dumps({'segments': [{
        'kind': 'narration', 'speaker_id': None, 'text': 'Someone says “hello.”'
    }], 'state': {'emotion': 'wary', 'rel_delta': 0}})
    prose, _ = extract_state_tag(decode_dialogue_response(raw, state()))
    assert present_dialogue(prose, state())[1] == [
        {'kind': 'narration', 'text': 'Someone says “hello.”'}
    ]


# --- Player-line echo (found by the Jev game arena on beta, 2026-09-23) -------
# Live beta rendered "Natsumi Saito: That sounds amazing. Do you all cook
# together usually?" - the PLAYER's exact message - as an NPC's dialogue.

def test_npc_segment_repeating_the_players_exact_line_is_dropped():
    _, blocks = present_dialogue(
        "[SPEAKER:mizuki]That sounds amazing. Do you all cook together usually?[/SPEAKER]", state())
    assert drop_player_echo(blocks, "That sounds amazing. Do you all cook together usually?") == []


def test_echoed_prefix_is_stripped_and_the_npcs_own_reply_kept():
    _, blocks = present_dialogue(
        "[SPEAKER:mizuki]That sounds amazing. Do you all cook together usually?\n\n"
        "Yeah, we try to. Tonight is stir-fry.[/SPEAKER]", state())
    out = drop_player_echo(blocks, "That sounds amazing. Do you all cook together usually?")
    assert [b["text"] for b in out] == ["Yeah, we try to. Tonight is stir-fry."]
    assert out[0]["speaker_id"] == "mizuki"


def test_echo_of_quoted_speech_inside_a_mixed_player_action_is_dropped():
    player = "Hey, I'm glad to be here! Coffee sounds great, thanks.\" I set my suitcase down. \"So, what’s for dinner?"
    _, blocks = present_dialogue(
        "The hallway is warm. [SPEAKER:iu]Hey, I'm glad to be here! Coffee sounds great, thanks.[/SPEAKER] "
        "[SPEAKER:iu]Dinner is stir-fry tonight.[/SPEAKER]", state())
    out = drop_player_echo(blocks, player)
    assert [b["kind"] for b in out] == ["narration", "dialogue"]
    assert out[1]["text"] == "Dinner is stir-fry tonight."


def test_player_attributed_echo_and_short_or_original_npc_lines_are_kept():
    player = "Yes. Do you all cook together usually?"
    state_with_player = state()
    state_with_player.characters["player"] = Character(key="player", name="Alex")
    _, blocks = present_dialogue(
        "[SPEAKER:player]Do you all cook together usually?[/SPEAKER]"
        "[SPEAKER:mizuki]Yes.[/SPEAKER]"
        "[SPEAKER:iu]We cook together on Sundays.[/SPEAKER]", state_with_player)
    assert drop_player_echo(blocks, player) == blocks


def test_contract_forbids_echoing_the_player():
    assert "Never repeat the player's own message" in dialogue_prompt(state())


# --- BL-22: markdown/quote wrappers leaked into dialogue segments on beta -----

@pytest.mark.parametrize("raw,expected", [
    ("**Great! We could use a little excitement.**", "Great! We could use a little excitement."),
    ('"Tea it is!"', "Tea it is!"),
    ("**“Tea it is!”**", "Tea it is!"),
    ("*Laughter echoes from the dining area.*", "*Laughter echoes from the dining area.*"),
    ("I said **never**, okay?", "I said **never**, okay?"),
])
def test_clean_spoken_text_strips_only_whole_line_wrappers(raw, expected):
    assert clean_spoken_text(raw) == expected


def test_structured_dialogue_segments_are_cleaned_on_decode():
    raw = json.dumps({"segments": [{"kind": "dialogue", "speaker_id": "mizuki", "text": "**Welcome home!**"}],
                      "state": {"emotion": "warm", "rel_delta": 0}})
    _, blocks = present_dialogue(extract_state_tag(decode_dialogue_response(raw, state()))[0], state())
    assert blocks[0]["text"] == "Welcome home!"


def test_contract_says_segment_text_is_plain_speech():
    assert "no quotation marks" in dialogue_prompt(state())


# --- BL-22: beta narrated from the focal housemate's POV and gave her the player's
# lines ("Mizuki Shida: You can just call me Mizuki. I'm really looking forward
# to settling in...", "her family's pasta recipe" - the player's pasta).

def test_contract_fixes_second_person_player_point_of_view():
    prompt = dialogue_prompt(state())
    assert "second person" in prompt
    assert "The player is not a cast member" in prompt


def test_player_can_never_be_an_ai_dialogue_speaker():
    s = state()
    s.characters["player"] = Character(key="player", name="Paul")
    schema = dialogue_response_format(s)["json_schema"]["schema"]
    speakers = schema["properties"]["segments"]["items"]["properties"]["speaker_id"]["enum"]
    assert "player" not in speakers
    assert '"player":' not in dialogue_prompt(s)
    raw = json.dumps({"segments": [
        {"kind": "dialogue", "speaker_id": "player", "text": "Hi, I'm Paul."},
        {"kind": "dialogue", "speaker_id": "mizuki", "text": "Welcome, Paul."},
    ], "state": {"emotion": "warm", "rel_delta": 0}})
    prose, _ = extract_state_tag(decode_dialogue_response(raw, s))
    assert "Hi, I'm Paul" not in prose
    assert present_dialogue(prose, s)[1][0]["speaker_id"] == "mizuki"
