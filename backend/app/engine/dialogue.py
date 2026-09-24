"""Speaker-aware presentation, independent of story rules and memory prose.

The model marks spoken passages using stable cast IDs. Only the server resolves
identities and portraits; unknown IDs never borrow the main character's face.
Plain prose remains valid for older saves and non-story command responses.
"""
from __future__ import annotations

import json
import re

from backend.app.engine.character_assets import resolve_character_avatar_url, DEFAULT_PERSONA_AVATAR

MARKER = re.compile(r"\[SPEAKER:([^\]\n]+)\]|\[/SPEAKER\]", re.I)


def dialogue_prompt(state) -> str:
    cast = {key: ch.name for key, ch in (state.characters or {}).items()}
    return (
        "\n\n[SPEAKER PRESENTATION CONTRACT]\n"
        "Return the JSON object required by the response schema. Its segments array "
        "contains the scene in reading order. Each segment has kind (narration or "
        "dialogue), speaker_id (null for narration, a cast ID for dialogue), and text. "
        "EVERY spoken passage MUST be a dialogue segment. Split at every change of "
        "speaker, including within one paragraph. Dialogue text contains only the "
        "spoken words: no quotation marks and no ** or other markdown, because the "
        "interface displays speech itself (this overrides any bold-quote formatting "
        "rule for prose). Keep actions and narration in "
        "narration segments. Do not add name prefixes inside spoken text. Never "
        "invent the player's dialogue. Never repeat the player's own message as anyone's "
        "dialogue; the player already sees what they wrote. Use speaker_id unknown for an unidentified "
        "or unlisted voice. Do not reveal "
        "a concealed identity through a speaker ID. These markers are presentation "
        "metadata; preserve all other story requirements. Put the focal character's "
        "emotion and relationship change (-1, 0, or 1) in the state object. Never "
        "write [[STATE]] tags in scene text. "
        "This JSON transport replaces prose-only output formatting.\nCast IDs: "
        + json.dumps(cast, ensure_ascii=False)
    )


def dialogue_response_format(state) -> dict:
    """Constrain speaker IDs and require an ordered scene on the generation call."""
    ids = list((getattr(state, "characters", {}) or {}).keys())
    return {"type": "json_schema", "json_schema": {
        "name": "story_scene", "strict": True,
        "schema": {"type": "object", "additionalProperties": False,
                   "required": ["segments", "state"], "properties": {
                       "segments": {"type": "array", "items": {
                           "type": "object", "additionalProperties": False,
                           "required": ["kind", "speaker_id", "text"], "properties": {
                               "kind": {"type": "string", "enum": ["narration", "dialogue"]},
                               "speaker_id": {"type": ["string", "null"], "enum": list(dict.fromkeys(ids + ["unknown", None]))},
                               "text": {"type": "string"},
                           }}},
                       "state": {"type": "object", "additionalProperties": False,
                                 "required": ["emotion", "rel_delta"], "properties": {
                                     "emotion": {"type": "string"},
                                     "rel_delta": {"type": "integer", "enum": [-1, 0, 1]},
                                 }},
                   }},
    }}


QUOTE_PAIRS = (('"', '"'), ("“", "”"), ("‘", "’"))


def clean_spoken_text(text: str) -> str:
    """Strip whole-line presentation wrappers from spoken dialogue.

    The prose-era storyteller rule "spoken lines must appear as **bold
    quotes**" leaks literal ``**...**`` / quotes into structured dialogue
    segments (BL-22, arena pilot 2026-09-23). Only a wrapper around the WHOLE
    line is removed; inner emphasis and single-asterisk actions are kept.
    """
    out = (text or "").strip()
    changed = True
    while changed and len(out) >= 2:
        changed = False
        if out.startswith("**") and out.endswith("**") and len(out) > 4 and "**" not in out[2:-2]:
            out, changed = out[2:-2].strip(), True
            continue
        for open_q, close_q in QUOTE_PAIRS:
            inner = out[1:-1]
            if out.startswith(open_q) and out.endswith(close_q) and open_q not in inner and close_q not in inner:
                out, changed = inner.strip(), True
                break
    return out


def _explicit_speaker_parts(text: str, state) -> list[tuple[str, str | None]]:
    """Split only unambiguous ``Canonical Name: speech`` lines from narration.

    This is a semantic guard for structured-output models that occasionally put
    an explicitly attributed line in a narration segment. It deliberately does
    not guess speakers from bare quotation marks or surrounding prose.
    """
    characters = getattr(state, "characters", {}) or {}
    names = sorted(
        ((str(ch.name).strip(), key) for key, ch in characters.items() if str(ch.name).strip()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    if not names:
        return [(text, None)]
    alternatives = "|".join(re.escape(name) for name, _ in names)
    pattern = re.compile(rf"^\s*({alternatives})\s*:\s*(?=[\"“‘'])", re.I)
    ids = {name.casefold(): key for name, key in names}
    parts: list[tuple[str, str | None]] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        match = pattern.match(paragraph)
        if match:
            parts.append((paragraph[match.end():].strip(), ids[match.group(1).casefold()]))
        else:
            parts.append((paragraph, None))
    return parts or [(text, None)]


def decode_dialogue_response(raw: str, state=None) -> str:
    """Bridge structured generation into the existing state-tag pipeline.

    Retain compatibility with older model adapters returning ordinary prose.
    Authored openings and translation use the same small marker parser.
    """
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        if isinstance(raw, str) and raw.lstrip().startswith("{"):
            raise ValueError("Incomplete structured scene") from None
        return raw
    if not isinstance(value, dict) or not isinstance(value.get("segments"), list):
        return raw
    parts = []
    for segment in value["segments"]:
        if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
            continue
        # Transport markers within text cannot override the structured speaker.
        text = MARKER.sub("", segment["text"])
        text = re.sub(r"\[\[STATE\]\].*?(?:\[\[/STATE\]\]|$)", "", text, flags=re.S)
        if segment.get("kind") == "dialogue":
            text = clean_spoken_text(text)
            speaker = segment.get("speaker_id") or "unknown"
            if not isinstance(speaker, str) or not re.fullmatch(r"[\w.-]+", speaker):
                speaker = "unknown"
            parts.append(f"[SPEAKER:{speaker}]{text}[/SPEAKER]")
        elif state is not None:
            for part, speaker in _explicit_speaker_parts(text, state):
                parts.append(f"[SPEAKER:{speaker}]{part}[/SPEAKER]" if speaker else part)
        else:
            parts.append(text)
    if isinstance(value.get("state"), dict):
        parts.append("[[STATE]]" + json.dumps(value["state"]) + "[[/STATE]]")
    return "\n\n".join(parts)


def _segment(text: str, speaker: str | None, characters: dict) -> dict:
    if speaker is None:
        return {"kind": "narration", "text": text}
    ch = characters.get(speaker)
    name = ch.name if ch else "Unknown voice"
    # Only authored local image paths are exposed, never arbitrary model URLs.
    meta = (getattr(ch, "meta", None) or {}) if ch else {}
    portrait = meta.get("portrait_url") or meta.get("avatar_url")
    if not isinstance(portrait, str) or not portrait.startswith("/img/") or ".." in portrait:
        portrait = resolve_character_avatar_url(speaker, name) if ch else DEFAULT_PERSONA_AVATAR
    return {"kind": "dialogue", "speaker_id": speaker if ch else None,
            "speaker_name": name, "portrait_url": portrait, "text": text}


def present_dialogue(text: str, state) -> tuple[str, list[dict]]:
    """Strip transport markers and return ordered, validated presentation blocks.

    An unclosed marker runs to end of reply; nested markers switch speaker.
    Untagged legacy paragraphs are retained as narration, without guessing.
    """
    characters = getattr(state, "characters", {}) or {}
    segments = []
    speaker = None
    offset = 0
    for match in MARKER.finditer(text):
        body = text[offset:match.start()].strip()
        if body:
            segments.append(_segment(body, speaker, characters))
        speaker = match.group(1).strip() if match.group(1) is not None else None
        offset = match.end()
    body = text[offset:].strip()
    if body:
        segments.append(_segment(body, speaker, characters))
    clean = MARKER.sub("", text).strip()
    grouped = []
    for segment in segments:
        if (grouped and segment["kind"] == "dialogue" and grouped[-1]["kind"] == "dialogue"
                and segment.get("speaker_id") is not None
                and segment.get("speaker_id") == grouped[-1].get("speaker_id")):
            grouped[-1]["text"] += "\n\n" + segment["text"]
        else:
            grouped.append(segment)
    return clean, grouped


SENTENCE = re.compile(r"[^.!?…]+[.!?…]*[\"'”’]*")
MIN_ECHO_WORDS = 3


def normalized_words(text: str) -> str:
    return " ".join(re.findall(r"[\w']+", (text or "").casefold().replace("’", "'")))


def drop_player_echo(segments: list[dict], player_message: str, player_key: str = "player") -> list[dict]:
    """Remove the player's own words from other speakers' dialogue.

    The structured scene forces every spoken passage onto a speaker_id, so when
    the model echoes the player's line it sometimes attributes it to a nearby
    NPC (live beta 2026-09-23: "Natsumi Saito: That sounds amazing. Do you all
    cook together usually?" was the player's exact message). Leading sentences
    of a non-player dialogue segment that appear verbatim (word-normalized, at
    least MIN_ECHO_WORDS words) in the player's message are stripped; a segment
    that was only the echo is dropped. Short lines ("Yes.") and the NPC's own
    words are never touched.
    """
    said = f" {normalized_words(player_message)} "
    if not said.strip():
        return segments
    out = []
    for seg in segments:
        if seg.get("kind") == "dialogue" and seg.get("speaker_id") != player_key:
            text, cut = seg["text"], 0
            for match in SENTENCE.finditer(text):
                words = normalized_words(match.group())
                if not words:
                    cut = match.end()
                    continue
                if len(words.split()) >= MIN_ECHO_WORDS and f" {words} " in said:
                    cut = match.end()
                    continue
                break
            if cut:
                rest = text[cut:].strip()
                if not rest:
                    continue
                seg = {**seg, "text": rest}
        out.append(seg)
    return out


def encode_dialogue(segments: list[dict]) -> str:
    """Round-trip speaker boundaries through translation without translating IDs."""
    return "\n\n".join(
        f'[SPEAKER:{s.get("speaker_id") or "unknown"}]{s["text"]}[/SPEAKER]'
        if s["kind"] == "dialogue" else s["text"] for s in segments
    )


def dialogue_transcript(segments: list[dict]) -> str:
    """Keep attribution in LLM memory and fact extraction after removing tags."""
    return "\n\n".join(
        f'{s["speaker_name"]}: {s["text"]}' if s["kind"] == "dialogue" else s["text"]
        for s in segments
    )
