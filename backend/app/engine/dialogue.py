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
        "speaker, including within one paragraph. Keep actions and narration in "
        "narration segments. Do not add name prefixes inside spoken text. Never "
        "invent the player's dialogue. Use speaker_id unknown for an unidentified "
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


def decode_dialogue_response(raw: str) -> str:
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
            speaker = segment.get("speaker_id") or "unknown"
            if not isinstance(speaker, str) or not re.fullmatch(r"[\w.-]+", speaker):
                speaker = "unknown"
            text = f"[SPEAKER:{speaker}]{text}[/SPEAKER]"
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
