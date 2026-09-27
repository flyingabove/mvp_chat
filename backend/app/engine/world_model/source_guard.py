"""Keep claims about what the player said tied to witnessed utterances.

An NPC can be mistaken or lie about the world. A categorical attribution to
the player is different: it must have a matching utterance that this speaker
actually heard. This gate only edits the source attribution in generated
dialogue; it does not decide whether the player's statement was true.
"""
from __future__ import annotations

import re

from backend.app.engine.world_model.model import PLAYER, WorldModel

_SENTENCE = re.compile(r"[^.!?]+[.!?]*")
_WORDS = re.compile(r"[a-z']+", re.I)
_STOP = {"a", "an", "and", "as", "at", "about", "be", "been", "but", "for", "from",
         "had", "has", "have", "he", "her", "him", "i", "in", "is", "it", "me", "my",
         "of", "on", "or", "our", "she", "that", "the", "their", "there", "these",
         "they", "this", "those", "to", "was", "were", "we", "what", "who", "with",
         "you", "your", "said", "say", "mentioned", "mention", "told", "tell"}
_REPAIR = "I may be mixing up who told me that."


def _content(text: str) -> set[str]:
    return {word.lower() for word in _WORDS.findall(text) if word.lower() not in _STOP}


def _witnessed_statements(model: WorldModel, listener: str) -> list[str]:
    heard = {o.event_id for o in model.epistemics.observations
             if o.owner == listener and o.channel == "heard"}
    return [str(event.payload.get("text") or "") for event in model.world.events
            if event.id in heard and event.kind == "utterance"
            and event.payload.get("speaker") == PLAYER
            and "?" not in str(event.payload.get("text") or "")
            and not re.search(r"\b(?:didn't|did not|never|no|not)\b",
                              str(event.payload.get("text") or ""), re.I)]


def _supported(claim: str, statements: list[str]) -> bool:
    claim_words = _content(claim)
    if len(claim_words) < 2:
        return False
    return any(len(claim_words & _content(statement)) >= max(2, int(len(claim_words) * .7 + .999))
               for statement in statements)


def ground_player_attribution(model: WorldModel, speaker_id: str, text: str) -> str:
    """Correct unsupported generated claims that the NPC heard the player say X."""
    player_name = (model.player_name or "").strip()
    if not player_name or player_name == "the player" or not text:
        return text
    name = re.escape(player_name)
    named = re.compile(rf"\b(?:{name}|you)\s+(?:had\s+)?(?:told|said|mentioned)\b", re.I)
    indirect = re.compile(rf"\b(?:{name}|you)\b.{0,30}\b(?:told|said|mentioned)\b", re.I)
    pronoun = re.compile(r"\b(?:she|he|they)\s+(?:had\s+)?(?:told|said|mentioned)\b", re.I)
    statements = _witnessed_statements(model, speaker_id)
    pieces: list[str] = []
    player_antecedent = False
    for match in _SENTENCE.finditer(text):
        sentence = match.group().strip()
        if not sentence:
            continue
        source = named.search(sentence) or indirect.search(sentence)
        if source is None and player_antecedent:
            source = pronoun.search(sentence)
        if source is not None:
            claim = sentence[source.end():].strip(" ,.:;!?")
            if not _supported(claim, statements):
                sentence = _REPAIR
        pieces.append(sentence)
        player_antecedent = bool(re.search(rf"\b{name}\b", match.group(), re.I))
    return " ".join(pieces)
