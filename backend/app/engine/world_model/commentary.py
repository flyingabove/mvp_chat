"""The studio panel: commentators who only know what the cameras saw.

The dossier is built locally from committed events the player took part in,
in filmed places: behavior, things said aloud, social acts and their
answers, exits. Standings, private feelings, memories, disputes (a
listener's private perception) and unfilmed rooms never enter it. Each
panelist appraises the same footage with their own tastes. On the finale
turn the panel is written by the same response call as the exit scene.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from backend.app.engine.character_assets import DEFAULT_PERSONA_AVATAR
from backend.app.engine.world_model.model import PLAYER, WorldModel

FOOTAGE_KINDS = frozenset({"behavior", "self_claim", "confess_accepted", "confess_declined",
                           "ask_leave_together_accepted", "ask_leave_together_declined", "relationship_withdrawn",
                           "romance_ending", "solo_ending", "agreement_completed", "romance_relationship"})
ACT_KINDS = FOOTAGE_KINDS - {"behavior", "self_claim"}
INTERNAL = re.compile(r"\b(score|standing|tier|points?|dealbreaker|requirement|track|engine)\b", re.I)


@dataclass(frozen=True)
class Panelist:
    id: str
    name: str
    role: str
    tastes: dict[str, float]


@dataclass(frozen=True)
class Commentary:
    panelists: tuple[Panelist, ...]
    unfilmed_places: frozenset[str]
    segments: int = 6


@dataclass(frozen=True)
class FootageItem:
    event_id: str
    minute: int
    kind: str
    text: str
    tag: str = ""


def commentary_for(story_cfg: dict[str, Any]) -> Optional[Commentary]:
    raw = (story_cfg or {}).get("commentary")
    if not raw:
        return None
    panelists = tuple(Panelist(str(p.get("id") or ""), str(p.get("name") or ""), str(p.get("role") or ""),
                               {str(k): float(v) for k, v in (p.get("tastes") or {}).items()})
                      for p in raw.get("panelists") or [])
    if not panelists or any(not p.id or not p.name for p in panelists):
        raise ValueError("commentary needs panelists with id and name")
    if len({p.id for p in panelists}) != len(panelists):
        raise ValueError("panelist ids must be unique")
    return Commentary(panelists, frozenset(raw.get("unfilmed_places") or []), int(raw.get("segments") or 6))


def dossier(model: WorldModel, commentary: Commentary) -> list[FootageItem]:
    """Filmed, committed events the player took part in, as the cameras would show them."""
    names = model.names()
    items = []
    for event in model.world.events:
        if event.kind not in FOOTAGE_KINDS or PLAYER not in event.participants \
                or event.place in commentary.unfilmed_places:
            continue
        if event.kind == "behavior":
            actor, target, tag = event.payload.get("actor"), event.payload.get("target"), event.payload.get("tag")
            text = f"{names.get(actor, actor)} was {tag.replace('_', ' ')} toward {names.get(target, target)}"
            items.append(FootageItem(event.id, event.minute, event.kind, text, tag if actor == PLAYER else ""))
        else:
            text = re.sub(r"@(\w+)", lambda m: names.get(m.group(1), m.group(1)), event.truth)
            items.append(FootageItem(event.id, event.minute, event.kind, text))
    return items


def stances(commentary: Commentary, footage: list[FootageItem]) -> dict[str, tuple[str, Optional[str], Optional[str]]]:
    """Each panelist's leaning plus the filmed moment they liked most and least."""
    out = {}
    for panelist in commentary.panelists:
        scored = [(panelist.tastes.get(item.tag, 0.0), item) for item in footage if item.tag]
        total = sum(weight for weight, _ in scored)
        leaning = "warm" if total > 0.5 else "critical" if total < -0.5 else "mixed"
        best = max(scored, key=lambda s: s[0], default=(0, None))
        worst = min(scored, key=lambda s: s[0], default=(0, None))
        out[panelist.id] = (leaning, best[1].text if best[1] and best[0] > 0 else None,
                            worst[1].text if worst[1] and worst[0] < 0 else None)
    return out


def outline(commentary: Commentary, footage: list[FootageItem]) -> list[FootageItem]:
    """Acts and exits always; then the behavior panelists feel most strongly about; in time order."""
    acts = [item for item in footage if item.kind in ACT_KINDS]
    others = [item for item in footage if item.kind not in ACT_KINDS]
    strength = {id(item): sum(abs(p.tastes.get(item.tag, 0.0)) for p in commentary.panelists) for item in others}
    room = max(0, commentary.segments - len(acts))
    chosen = acts + sorted(others, key=lambda i: (-strength[id(i)], i.minute))[:room]
    return sorted(chosen, key=lambda i: i.minute)


def finale_directive(commentary: Commentary, footage: list[FootageItem]) -> str:
    moments = outline(commentary, footage)
    leanings = stances(commentary, footage)
    names = ", ".join(p.name for p in commentary.panelists)
    lines = [f"AFTER the exit scene, write THE STUDIO PANEL: {names} discuss the player's time in the house, as "
             f"dialogue segments with speaker_id {', '.join(p.id for p in commentary.panelists)}, about "
             f"{max(4, len(moments) + 2)} exchanges, ending with one verdict line from each panelist.",
             "Use ONLY this footage (never private thoughts, anything off camera, or any score or rule):"]
    lines += [f"- {item.text}" for item in moments] or ["- (little was filmed; they discuss how quiet the stay was)"]
    for panelist in commentary.panelists:
        leaning, liked, disliked = leanings[panelist.id]
        detail = "; ".join(x for x in (f"liked: {liked}" if liked else "", f"disliked: {disliked}" if disliked else "")
                           if x)
        lines.append(f"{panelist.name} ({panelist.role}) leans {leaning}" + (f" ({detail})" if detail else "") + ".")
    lines.append("Judge the player's behavior, never their worth; no mocking appearance or identity, no piling on.")
    return "\n".join(lines)


def fallback_panel(commentary: Commentary, footage: list[FootageItem]) -> list[dict]:
    """A short footage-only panel when the reply omitted it (counted as a canned recovery)."""
    lines = []
    for panelist in commentary.panelists:
        leaning, liked, disliked = stances(commentary, footage)[panelist.id]
        if leaning == "warm" and liked:
            text = f"I keep thinking about that moment: {liked}. That was sweet."
        elif leaning == "critical" and disliked:
            text = f"Come on. {disliked}. The cameras saw that."
        else:
            text = "Hard to call. They kept a lot to themselves on camera."
        lines.append({"kind": "dialogue", "speaker_id": panelist.id, "speaker_name": panelist.name,
                      "portrait_url": DEFAULT_PERSONA_AVATAR, "text": text})
    return lines


def scrub_panel(segments: list[dict], commentary: Commentary) -> int:
    """Keep the panel in its closing section and free of internal mechanics. Returns repairs made.

    Panelists are in a studio, not the house: a panel-labelled line before
    the closing run of panel lines was really a house line, so it becomes
    narration. Panel lines that mention scores/tiers/rules are dropped.
    """
    ids = {p.id for p in commentary.panelists}
    start = len(segments)
    while start > 0 and segments[start - 1].get("speaker_id") in ids:
        start -= 1
    repairs = 0
    for segment in segments[:start]:
        if segment.get("speaker_id") in ids:
            text = str(segment.get("text") or "")
            segment.clear()
            segment.update({"kind": "narration", "text": f"“{text}”"})
            repairs += 1
    leaked = [s for s in segments if s.get("speaker_id") in ids and INTERNAL.search(str(s.get("text") or ""))]
    for segment in leaked:
        segments.remove(segment)
    return repairs + len(leaked)
