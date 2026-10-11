"""Engine-chosen speakers: 1-3 per beat, instead of a model-chosen roll call.

Score = addressed (+5) / mentioned (+2) / warmth toward the player (+1 scaled)
/ topic overlap with an open thread (+2) / recency penalty (-2 last turn, -1
the turn before) / rotating initiative for the one longest-silent person (+1.5;
nobody gets it when several are tied, e.g. before anyone has spoken) / the speaker's own stances (BL-101: up to +1.5
when the subject is someone they are protective of, resent, are drawn to or rival over; -1 for someone who distrusts
the player and was not addressed).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, Iterable

from backend.app.engine.world_model.model import PLAYER, SpeakerPlan
from backend.app.engine.world_model.threads import active_thread_topics

if TYPE_CHECKING:
    from backend.app.engine.world_model.model import WorldModel

GROUP_ADDRESS = re.compile(r"\b(everyone|everybody|you all|y'all|you guys|guys|all of you|anyone|anybody|"
                           r"the (?:other )?(?:guys|girls|others|rest))\b", re.I)
CLOSE_SCORE = 1.0
STANCE_PULL = {"protective_of": 1.5, "resents": 1.0, "rival": 1.0, "crush": 0.8, "admires": 0.4, "ally": 0.3}
STANCE_CAP = 1.5
INTERJECT_AT = 0.8          # a stance pull this strong lets someone chime in even when another person was addressed
DISTRUST_HUSH = 1.0


def stance_pull(model: "WorldModel", cid: str, subjects: set[str]) -> float:
    """How much the speaker's own stances make them want to speak about these people (`subjects`): toward them, or, for a
    rival, about the person they both want. Capped so an addressed person still outranks it."""
    pull = 0.0
    for stance in model.stances.of(cid):
        weight = STANCE_PULL.get(stance.kind, 0.0)
        if weight and (stance.target in subjects or (stance.kind == "rival" and stance.about in subjects)):
            pull += weight * min(1.0, stance.strength)
    return min(STANCE_CAP, pull)
MAX_SPEAKERS = 3


def _name_terms(name: str, cid: str) -> list[str]:
    terms = {cid.replace("_", " "), name}
    terms.update(part.strip('"') for part in name.split() if len(part.strip('"')) >= 3)
    return [t for t in terms if t]


def addressed_ids(model: "WorldModel", message: str, candidates: Iterable[str]) -> tuple[set[str], set[str]]:
    """(addressed, mentioned): addressed = named at the start or in a vocative; mentioned = named anywhere."""
    addressed, mentioned = set(), set()
    text = message or ""
    for cid in candidates:
        character = model.characters[cid]
        for term in _name_terms(character.name, cid):
            pattern = rf"\b{re.escape(term)}\b"
            if not re.search(pattern, text, re.I):
                continue
            mentioned.add(cid)
            if re.search(rf"(^|[.!?]\s*|\b(?:hey|hi|so|okay|ok),?\s*){pattern}\s*[,!?:]", text, re.I) \
                    or re.search(rf"\b(?:turn|say|ask|tell|look)\w*\s+(?:to\s+)?{pattern}", text, re.I) \
                    or re.search(rf",\s*{pattern}\s*[?.!]?\s*$", text, re.I):
                addressed.add(cid)
            break
    return addressed, mentioned


def select_speakers(model: "WorldModel", candidates: list[str], message: str,
                    warmth: Callable[[str], float] = lambda cid: 0.0,
                    owes_answer: Iterable[str] = ()) -> SpeakerPlan:
    """`owes_answer`: characters with an open question from the player; they
    rank like someone addressed this turn."""
    candidates = [c for c in candidates if c in model.characters and model.characters[c].can_hear]
    if not candidates:
        return SpeakerPlan(reason="nobody present can talk")
    turn = model.turn
    addressed, mentioned = addressed_ids(model, message, candidates)
    addressed |= set(owes_answer) & set(candidates)
    words = {w.lower() for w in re.findall(r"[\w']+", message or "")}
    silence = {c: model.characters[c].turns_since_spoke(turn) for c in candidates}
    longest = max(silence.values())
    tied = [c for c in candidates if silence[c] == longest]
    silent_longest = tied[0] if len(tied) == 1 else ""
    scores: dict[str, float] = {}
    pulls: dict[str, float] = {}
    for cid in candidates:
        character = model.characters[cid]
        score = 0.0
        score += 5.0 if cid in addressed else 2.0 if cid in mentioned else 0.0
        score += max(-1.0, min(1.0, warmth(cid)))
        score += 2.0 if active_thread_topics(model, cid) & words else 0.0
        pulls[cid] = stance_pull(model, cid, (addressed | mentioned) - {cid})
        score += pulls[cid]
        if cid not in addressed and model.stances.has(cid, "distrusts", PLAYER):
            score -= DISTRUST_HUSH                  # someone who distrusts the player does not volunteer
        since = character.turns_since_spoke(turn)
        score -= 2.0 if since == 1 else 1.0 if since == 2 else 0.0
        if cid == silent_longest and cid not in addressed:
            score += 1.5
        # Deterministic tie-break: seeded jitter per turn, never above 0.1.
        score += model.rng(f"speaker:{cid}", turn).random() * 0.1
        scores[cid] = score
    ranked = sorted(candidates, key=lambda c: scores[c], reverse=True)
    primary = ranked[0]
    group = bool(GROUP_ADDRESS.search(message or "")) or len(addressed) > 1
    secondary = []
    for cid in ranked[1:]:
        if len(secondary) + 1 >= MAX_SPEAKERS:
            break
        if cid in addressed or (group and scores[cid] > 0) or scores[primary] - scores[cid] <= CLOSE_SCORE                 or pulls[cid] >= INTERJECT_AT:
            secondary.append(cid)
    if not group and not (addressed - {primary}):
        secondary = secondary[:1]
    chosen = [primary, *secondary]
    initiative = silent_longest if silent_longest and silent_longest in chosen and silent_longest not in addressed else ""
    reason = "addressed" if primary in addressed else "group address" if group else "scene flow"
    return SpeakerPlan(primary=primary, secondary=secondary, initiative=initiative,
                       silent_present=[c for c in candidates if c not in chosen], reason=reason)
