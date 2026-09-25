"""Speaker-aware presentation, independent of story rules and memory prose.

The model marks spoken passages using stable cast IDs. Only the server resolves
identities and portraits; unknown IDs never borrow the main character's face.
Plain prose remains valid for older saves and non-story command responses.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from backend.app.engine.character_assets import resolve_character_avatar_url, DEFAULT_PERSONA_AVATAR

MARKER = re.compile(r"\[SPEAKER:([^\]\n]+)\]|\[/SPEAKER\]", re.I)
QUOTED_SPEECH = re.compile(r'“([^”\n]{2,})”|"([^"\n]{2,})"')


def _contract_cast_ids(state) -> list[str]:
    """Cast IDs the storyteller may voice: never the player, and never a
    rotating-cast member who has not arrived (or has left). Listing all 17
    Six Strangers names let the model mention unarrived residents as if they
    lived there (live prod 2026-09-24: "Yuto should be back from practice")."""
    lifecycle = getattr(state, "cast_lifecycle", None)
    gated = lifecycle is not None and getattr(lifecycle, "enabled", False)
    return [key for key in (getattr(state, "characters", {}) or {})
            if key != "player" and (not gated or lifecycle.is_scene_eligible(key))]


def dialogue_prompt(state) -> str:
    cast = {key: state.characters[key].name for key in _contract_cast_ids(state)}
    return (
        "\n\n[SPEAKER PRESENTATION CONTRACT]\n"
        "Return the JSON object required by the response schema. Its segments array "
        "contains the scene in reading order. Each segment has kind (narration or "
        "dialogue), speaker_id (null for narration, a cast ID for dialogue), and text. "
        "EVERY spoken passage MUST be a dialogue segment. Split at every change of "
        "speaker, including within one paragraph. Break longer narration and a "
        "speaker's longer turn into readable scene beats of about 1-3 sentences "
        "each; keep their order and label EVERY dialogue beat with its speaker_id, "
        "even if the same person just spoke. Dialogue text contains only the "
        "spoken words: no quotation marks and no ** or other markdown, because the "
        "interface displays speech itself (this overrides any bold-quote formatting "
        "rule for prose). Keep actions and narration in "
        "narration segments. Do not add name prefixes inside spoken text. Never "
        "invent the player's dialogue. POINT OF VIEW: narration addresses the player in the "
        "second person (you) in present tense. The player is not a cast member: never "
        "narrate a housemate's thoughts as the player's, and never give a cast member "
        "the player's words, name, plans, possessions, or history (if the player says "
        "'call me Sam', nobody else says 'call me' with their own name). "
        "Never repeat the player's own message as anyone's "
        "dialogue; the player already sees what they wrote. Use speaker_id unknown for an unidentified "
        "or unlisted voice. A listed housemate introducing themselves is NOT an "
        "unknown voice: use their exact cast ID on every line, including their "
        "first greeting. Never substitute a first name or full name for the cast ID. Do not reveal "
        "a concealed identity through a speaker ID. These markers are presentation "
        "metadata; preserve all other story requirements. Put the focal character's "
        "emotion and relationship change (-1, 0, or 1) in the state object. Never "
        "write [[STATE]] tags in scene text. "
        "This JSON transport replaces prose-only output formatting.\nCast IDs: "
        + json.dumps(cast, ensure_ascii=False)
    )


def _allowed_speaker_ids(state) -> list[str]:
    """Contract cast narrowed to the world model's allowed speakers this turn
    (people physically present, unplaced characters, and the speaker plan)."""
    ids = _contract_cast_ids(state)
    view = getattr(getattr(state, "world_model", None), "view", None)
    allowed = set(getattr(view, "allowed_speakers", None) or [])
    narrowed = [key for key in ids if key in allowed]
    return narrowed or ids


def dialogue_response_format(state) -> dict:
    """Constrain speaker IDs and require an ordered scene on the generation call."""
    ids = _allowed_speaker_ids(state)
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
        ((str(ch.name).strip(), key) for key, ch in characters.items()
         if key != "player" and str(ch.name).strip()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    if not names:
        return [(text, None)]
    alternatives = "|".join(re.escape(name) for name, _ in names)
    pattern = re.compile(rf"^\s*({alternatives})\s*:\s*(?=\S)", re.I)
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
            if segment.get("speaker_id") == "player":
                continue
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


def _self_identified_speaker(text: str, state) -> str | None:
    """Resolve only a clear first-person full-name introduction by active cast."""
    characters = getattr(state, "characters", {}) or {}
    lifecycle = getattr(state, "cast_lifecycle", None)
    active = set(lifecycle.active_ids()) if lifecycle else set(characters)
    matches = []
    for key in active:
        if key == "player" or key not in characters:
            continue
        name = str(characters[key].name).strip()
        if name and re.match(rf"^\s*(?:and\s+)?(?:i['’]m|i am|my name is)\s+{re.escape(name)}(?=\b|[,.!?])",
                             text, re.I):
            matches.append(key)
    return matches[0] if len(matches) == 1 else None


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
            resolved = _self_identified_speaker(body, state) if speaker == "unknown" else None
            segments.append(_segment(body, resolved or speaker, characters))
        speaker = match.group(1).strip() if match.group(1) is not None else None
        offset = match.end()
    body = text[offset:].strip()
    if body:
        resolved = _self_identified_speaker(body, state) if speaker == "unknown" else None
        segments.append(_segment(body, resolved or speaker, characters))
    clean = MARKER.sub("", text).strip()
    # Each authored/model segment is a readable scene beat, even when one
    # character speaks twice. Coalescing them recreated the giant bubble.
    return clean, segments


def _unmarked_quotes(text: str) -> list[tuple[int, int, str]]:
    """Find quoted passages outside trusted storyteller speaker markers."""
    found: list[tuple[int, int, str]] = []
    inside_speech = False
    offset = 0
    for marker in MARKER.finditer(text):
        if not inside_speech:
            for quote in QUOTED_SPEECH.finditer(text, offset, marker.start()):
                found.append((quote.start(), quote.end(), quote.group(1) or quote.group(2)))
        inside_speech = marker.group(1) is not None
        offset = marker.end()
    if not inside_speech:
        for quote in QUOTED_SPEECH.finditer(text, offset):
            found.append((quote.start(), quote.end(), quote.group(1) or quote.group(2)))
    return found[:20]


def has_unmarked_quotes(text: str) -> bool:
    """Whether a structured reply still contains speech Jev may need to label."""
    return bool(_unmarked_quotes(text))


async def attribute_unmarked_quotes(text: str, state, jev, *, timeout_ms: int = 1000) -> str:
    """Use one bounded Jev choice batch for quoted speech missed by JSON tags.

    Jev chooses among cast IDs, an unknown voice, and non-spoken quotation.
    Low-confidence or failed decisions leave the original prose untouched;
    this fallback must never invent a confident speaker or delay a turn for
    more than one short provider timeout.
    """
    from backend.app.llm.decisions.types import Criticality, Decision, DecisionBatch

    quotes = _unmarked_quotes(text)
    if not quotes:
        return text
    characters = getattr(state, "characters", {}) or {}
    lifecycle = getattr(state, "cast_lifecycle", None)
    active = set(lifecycle.active_ids()) if lifecycle else set(characters)
    cast = {key: str(ch.name) for key, ch in characters.items()
            if key != "player" and key in active}
    criteria = {"narration": "Quoted words are not spoken aloud in this scene",
                "unknown": "Spoken aloud, but the speaker cannot be identified reliably"}
    criteria.update({key: f"Spoken aloud by {name}" for key, name in cast.items()})
    decisions = tuple(Decision(
        id=f"quote_{i}", task="speaker_attribution", kind="choice",
        instructions=f"Classify quoted passage {i}: {quote!r}. Use the surrounding scene. "
                     "Choose a named speaker only when the scene clearly attributes the words; "
                     "otherwise choose unknown or narration.",
        criteria=criteria, criticality=Criticality.DEGRADABLE,
        allowed=frozenset(criteria), none_option="narration", min_confidence=.8,
    ) for i, (_, _, quote) in enumerate(quotes))
    batch = DecisionBatch(name="speaker_attribution", state=text[:6000], decisions=decisions)
    try:
        result = await jev.ask(batch, timeout_ms=timeout_ms)
    except Exception:
        return text
    replacements = []
    for i, (start, end, quote) in enumerate(quotes):
        answer = result.answers.get(f"quote_{i}")
        choice = getattr(answer, "choice", None)
        confidence = getattr(answer, "confidence", None)
        if (getattr(answer, "kind", None) == "choice" and choice in criteria
                and choice != "narration" and isinstance(confidence, (int, float))
                and confidence >= .8):
            replacements.append((start, end, f"[SPEAKER:{choice}]{clean_spoken_text(quote)}[/SPEAKER]"))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


SENTENCE = re.compile(r"[^.!?…]+[.!?…]*[\"'”’]*")
MIN_ECHO_WORDS = 3
# Share of a passage's words that must appear, in order, in the player's
# message for it to count as a reworded echo ("That sounds great." for
# "sounds great"). Word order matters, so an NPC reusing a few of the
# player's words in its own reply stays well below this.
ECHO_COVERAGE = 0.8
# A single leading sentence counts as a reworded echo only when it is long and
# almost entirely the player's words, so short agreement ("Me too!") survives.
REWORDED_MIN_WORDS = 6
REWORDED_COVERAGE = 0.85
# Recent-reply repetition: dialogue this long, or narration this long, that
# already appeared in the last few replies is a copy, not a new beat.
REPEAT_MIN_DIALOGUE_WORDS = 4
REPEAT_MIN_NARRATION_WORDS = 8


def normalized_words(text: str) -> str:
    return " ".join(re.findall(r"[\w']+", (text or "").casefold().replace("’", "'")))


def _echo_coverage(words: list[str], said: list[str]) -> float:
    if not words:
        return 0.0
    blocks = SequenceMatcher(None, words, said, autojunk=False).get_matching_blocks()
    return sum(block.size for block in blocks) / len(words)


def drop_player_echo(segments: list[dict], player_message: str, player_key: str = "player") -> list[dict]:
    """Remove the player's own words from other speakers' dialogue.

    The structured scene forces every spoken passage onto a speaker_id, so when
    the model echoes the player's line it sometimes attributes it to a nearby
    NPC (live beta 2026-09-23: "Natsumi Saito: That sounds amazing. Do you all
    cook together usually?" was the player's exact message; live prod
    2026-09-24: "Makoto: Cool! Where are all the other guys at? I want to say
    hi."). The longest run of leading sentences that appears verbatim
    (word-normalized) in the player's message is stripped once it reaches
    MIN_ECHO_WORDS words, so a short interjection ("Cool!") no longer hides
    the echo behind it. A whole segment that is a lightly reworded copy of
    the message (ECHO_COVERAGE of its words, in order) is dropped. Short
    lines ("Yes.") and the NPC's own words are never touched.
    """
    said_words = normalized_words(player_message).split()
    said = f" {' '.join(said_words)} "
    if not said.strip():
        return segments
    out = []
    orphan_tag_next = False
    for seg in segments:
        if seg.get("kind") == "dialogue" and seg.get("speaker_id") != player_key:
            text, cut, run = seg["text"], 0, []
            for match in SENTENCE.finditer(text):
                words = normalized_words(match.group()).split()
                if not words:
                    if len(run) >= MIN_ECHO_WORDS:
                        cut = match.end()
                    continue
                if f" {' '.join(run + words)} " not in said:
                    # A long sentence copied with a word added or dropped
                    # ("...after a long day too.") is still the player's line.
                    if len(words) >= REWORDED_MIN_WORDS and _echo_coverage(words, said_words) >= REWORDED_COVERAGE:
                        run, cut = [], match.end()
                        continue
                    break
                run += words
                if len(run) >= MIN_ECHO_WORDS:
                    cut = match.end()
            seg_words = normalized_words(text).split()
            whole_echo = (len(seg_words) >= MIN_ECHO_WORDS + 1
                          and _echo_coverage(seg_words, said_words) >= ECHO_COVERAGE
                          and _echo_coverage(said_words, seg_words) >= ECHO_COVERAGE)
            rest = text[cut:].strip() if cut else text
            if whole_echo or not rest:
                _drop_leading_tag(out)
                orphan_tag_next = True
                continue
            if cut:
                seg = {**seg, "text": rest}
        elif seg.get("kind") == "narration" and orphan_tag_next:
            seg = _without_orphan_tag(seg)
            orphan_tag_next = False
            if seg is None:
                continue
        orphan_tag_next = False
        out.append(seg)
    return out


# A narration beat that only attributes speech ("you murmur, ...", "You
# whisper,"). Lowercase openings are continuations of the removed line.
SPEECH_TAG = re.compile(
    r"^\s*(?:(?:you|he|she|they)\s+)?(?:(?:lean\s+in\s+and|quietly|softly)\s+)?"
    r"(?:say|says|said|murmur|murmurs|murmured|whisper|whispers|whispered|ask|asks|asked|"
    r"reply|replies|replied|answer|answers|answered|add|adds|added|mutter|mutters|muttered|"
    r"breathe|breathes|breathed|call|calls|called|promise|promises|promised|continue|continues|continued)\b",
    re.I)
SENTENCE_END = re.compile(r"[.!?…][\"'”’]*(?=\s|$)")


def _without_orphan_tag(seg: dict) -> dict | None:
    """Strip the speech tag that attributed a just-removed echo (arena
    promote_37bbcb2, IU t3: "you murmur, your voice steadying with resolve."
    survived its line and read as narrating the player's action). Only the
    first sentence is examined; ordinary narration is returned unchanged."""
    text = seg.get("text", "").lstrip()
    first_end = SENTENCE_END.search(text)
    first = text[:first_end.end()] if first_end else text
    if not (SPEECH_TAG.match(first) or first[:1].islower()):
        return seg
    rest = text[len(first):].strip()
    return {**seg, "text": rest} if rest else None


def _drop_leading_tag(out: list[dict]) -> None:
    """Remove a trailing "You lean in and whisper," that introduced a removed echo."""
    if not out or out[-1].get("kind") != "narration":
        return
    text = out[-1]["text"].rstrip()
    if not text.endswith((",", ":")):
        return
    ends = list(SENTENCE_END.finditer(text))
    kept = text[:ends[-1].end()].strip() if ends else ""
    if kept:
        out[-1] = {**out[-1], "text": kept}
    else:
        out.pop()


def drop_repeated_lines(segments: list[dict], recent_replies: list[str]) -> list[dict]:
    """Remove beats copied verbatim from the storyteller's recent replies.

    Live prod 2026-09-24: every turn re-sent the opening's "You found it. Come
    in; we're just setting the table." Each copy went back into the history
    the model reads, so the repeats snowballed. A dialogue segment (at least
    REPEAT_MIN_DIALOGUE_WORDS words) or narration segment (at least
    REPEAT_MIN_NARRATION_WORDS) whose word-normalized text already appears in
    a recent reply is dropped. If every segment is a repeat, the reply is
    returned unchanged rather than emptied.
    """
    seen = _recent_text(recent_replies)
    kept = [seg for seg in segments if not _is_repeat(seg, seen)]
    return kept or segments


def only_repeats(segments: list[dict], recent_replies: list[str]) -> bool:
    """True when every beat of a reply was already said in recent replies."""
    seen = _recent_text(recent_replies)
    return bool(segments) and all(_is_repeat(seg, seen) for seg in segments)


def _recent_text(recent_replies: list[str]) -> str:
    return " ".join(f" {normalized_words(reply)} " for reply in recent_replies if reply)


def _is_repeat(seg: dict, seen: str) -> bool:
    if not seen.strip():
        return False
    words = normalized_words(seg.get("text", ""))
    minimum = REPEAT_MIN_DIALOGUE_WORDS if seg.get("kind") == "dialogue" else REPEAT_MIN_NARRATION_WORDS
    return len(words.split()) >= minimum and f" {words} " in seen


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
