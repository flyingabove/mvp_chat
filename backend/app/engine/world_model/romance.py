"""Validated, voluntary joint-departure decision for opted-in social stories."""
from __future__ import annotations

import re
from typing import Any

from backend.app.engine.world_model import bootstrap
from backend.app.engine.world_model.model import PLAYER


def _eligible_present(state: Any) -> set[str]:
    model = getattr(state, "world_model", None)
    cfg = getattr(state, "story_cfg", {}) or {}
    if model is None or not isinstance(cfg, dict):
        return set()
    goal = ((cfg.get("mode") or {}).get("romance_goal") or {})
    gender = str(getattr(state, "gender", "") or "").upper()
    if not goal.get("enabled") or goal.get("partner_gender") != "opposite_player" or gender not in {"M", "F"}:
        return set()
    active = set(bootstrap.eligible_ids(state)) & set(model.characters)
    genders = {str(char.get("key")): str(char.get("gender") or "").upper()
               for char in cfg.get("characters") or [] if isinstance(char, dict)}
    return {cid for cid in active & set(model.present_with_player())
            if genders.get(cid) in {"M", "F"} and genders[cid] != gender}


def _player_names(text: str, model: Any, present: set[str]) -> list[str]:
    return [cid for cid in sorted(present)
            if re.search(rf"\b(?:{re.escape(model.characters[cid].name)}|{re.escape(cid)})\b", text, re.I)]


def _current_utterance_ids(model: Any, speakers: set[str]) -> tuple[str, ...]:
    prefix = f"utterance:{model.turn}:"
    return tuple(event.id for event in model.world.events
                 if event.kind == "utterance" and event.operation_id.startswith(prefix)
                 and event.payload.get("speaker") in speakers)


def _relationship_choice(text: str, npc: bool) -> bool:
    words = str(text or "").strip().strip('"“”')
    if not re.match(r"^(?:yes[,!.]?\s*)?I\s+(?:want|choose|decide|would like)\s+to\s+", words, re.I):
        return False
    first_sentence = re.split(r"[.!?]", words, maxsplit=1)[0]
    if re.search(r"\b(?:not|never|maybe|might|if|force)\b", first_sentence, re.I):
        return False
    if not re.search(r"\b(?:date|be\s+(?:your|a)\s+(?:romantic\s+)?partner|be\s+with)\b",
                     first_sentence, re.I):
        return False
    return not npc or bool(re.search(r"\byou\b", first_sentence, re.I))


def _withdraws(text: str, topic: str) -> bool:
    words = str(text or "").strip().strip('"“”')
    return bool(re.match(r"^I\s+(?:do not|don't|cannot|can't|will not|won't)\s+"
                         r"(?:(?:want|choose|plan)\s+to\s+)?", words, re.I)
                and re.search(rf"\b(?:{topic})\b", words, re.I))


def record_relationship_decisions(state: Any, player_message: str, segments: list[dict]) -> bool:
    model = getattr(state, "world_model", None)
    present = _eligible_present(state)
    if model is None or not present or model.romance_outcome:
        return False
    partner = model.romance_relationship_partner
    if partner in present and _withdraws(player_message, r"date|be with|relationship"):
        model.romance_relationship_partner = ""
        model.romance_relationship_player_choice = ""
        model.romance_player_choice = ""
    for segment in segments or []:
        if (segment.get("kind") == "dialogue" and segment.get("speaker_id") == partner
                and partner in present and _withdraws(segment.get("text") or "", r"date|be with|relationship")):
            model.romance_relationship_partner = ""
            model.romance_relationship_npc_choice = ""
            model.romance_npc_choice = ""
    if _relationship_choice(player_message, npc=False):
        named = _player_names(player_message, model, present)
        if len(named) == 1:
            model.romance_relationship_player_choice = named[0]
    for segment in segments or []:
        speaker = segment.get("speaker_id")
        if segment.get("kind") != "dialogue" or speaker not in present:
            continue
        if _relationship_choice(segment.get("text") or "", npc=True):
            model.romance_relationship_npc_choice = speaker
    partner = model.romance_relationship_player_choice
    if partner and partner == model.romance_relationship_npc_choice and partner in present:
        if model.romance_relationship_partner != partner:
            model.romance_relationship_partner = partner
            model.world.add_event(model.world.minute, model.player_place(), (PLAYER, partner),
                                  f"The player and @{partner} mutually chose a romantic relationship",
                                  kind="romance_relationship", operation_id=f"romance:relationship:{model.turn}:{partner}",
                                  payload={"partner": partner},
                                  cause_ids=_current_utterance_ids(model, {PLAYER, partner}))
        return True
    return False


def _commits_to_depart(text: str) -> bool:
    """Conservative literal adapter until the turn extractor has typed acts.

    Requiring the actor's own first-person statement and romantic framing
    avoids counting narrator descriptions, friendly plans and secondhand claims.
    """
    words = str(text or "").strip().strip('"“”')
    if not re.match(r"^(?:yes[,!.]?\s*)?I\s+(?:choose|want|decide|plan|will|am going)\s+to\s+leave\b",
                    words, re.I):
        return False
    first_sentence = re.split(r"[.!?]", words, maxsplit=1)[0]
    if "?" in words.split(".")[0]:
        return False
    return (bool(re.search(r"\bwith\b", first_sentence, re.I))
            and bool(re.search(r"\b(?:romantic partner|as a couple|in a romantic relationship)\b",
                               first_sentence, re.I))
            and not re.search(r"\b(?:not|never|maybe|might|if|hypothetical|force|make you)\b",
                              first_sentence, re.I))


def record_departure_decisions(state: Any, player_message: str, segments: list[dict],
                               prior_relationship_partner: str | None = None) -> bool:
    model = getattr(state, "world_model", None)
    if model is None or model.romance_outcome:
        return bool(model and model.romance_outcome)
    present = _eligible_present(state)
    relationship_partner = model.romance_relationship_partner
    # A relationship established in this same generated turn is not enough;
    # both people must make a separate later departure decision. A breakup in
    # this turn also invalidates the prior relationship immediately.
    if (prior_relationship_partner is not None
            and relationship_partner != prior_relationship_partner):
        return False
    if not relationship_partner or relationship_partner not in present:
        return False
    if _withdraws(player_message, "leave"):
        model.romance_player_choice = ""
    for segment in segments or []:
        if (segment.get("kind") == "dialogue" and segment.get("speaker_id") == relationship_partner
                and _withdraws(segment.get("text") or "", "leave")):
            model.romance_npc_choice = ""
    if _commits_to_depart(player_message):
        for cid in _player_names(player_message, model, present):
            if cid == relationship_partner:
                model.romance_player_choice = cid
                model.world.add_event(model.world.minute, model.player_place(), (PLAYER, cid),
                                      f"The player chose a romantic departure with @{cid}",
                                      kind="relationship_decision", operation_id=f"romance:player:{model.turn}:{cid}",
                                      payload={"actor": PLAYER, "partner": cid},
                                      cause_ids=_current_utterance_ids(model, {PLAYER}))
                break
    for segment in segments or []:
        speaker = segment.get("speaker_id")
        if segment.get("kind") != "dialogue" or speaker != relationship_partner:
            continue
        if _commits_to_depart(segment.get("text") or "") and re.search(
                r"\bwith\s+you\b", str(segment.get("text") or ""), re.I):
            model.romance_npc_choice = speaker
            model.world.add_event(model.world.minute, model.player_place(), (speaker, PLAYER),
                                  f"@{speaker} chose a romantic departure with the player",
                                  kind="relationship_decision", operation_id=f"romance:npc:{model.turn}:{speaker}",
                                  payload={"actor": speaker, "partner": PLAYER},
                                  cause_ids=_current_utterance_ids(model, {speaker}))
    partner = model.romance_player_choice
    if partner and partner == model.romance_npc_choice and partner == relationship_partner and partner in present:
        model.romance_outcome = "mutual_departure"
        ending = model.world.add_event(model.world.minute, model.player_place(), (PLAYER, partner),
                              f"The player and @{partner} chose to leave the house together as a couple",
                              kind="romance_ending", visibility="public",
                              operation_id=f"romance:ending:{model.turn}:{partner}",
                              payload={"partner": partner},
                              cause_ids=tuple(event.id for event in model.world.events
                                              if event.kind in {"romance_relationship", "relationship_decision"}
                                              and partner in event.participants))
        lifecycle = getattr(state, "cast_lifecycle", None)
        if lifecycle is not None and getattr(lifecycle, "enabled", False):
            lifecycle.depart_for_ending(partner, minute=model.world.minute,
                                        event_id=f"{ending.id}:partner", reason="mutual romantic departure")
        model.world.remove(partner)
        model.world.remove(PLAYER)
        return True
    return False


def record_solo_departure(state: Any, player_message: str) -> bool:
    model = getattr(state, "world_model", None)
    cfg = getattr(state, "story_cfg", {}) or {}
    if model is None or model.romance_outcome or not isinstance(cfg, dict):
        return False
    if not ((cfg.get("mode") or {}).get("romance_goal") or {}).get("enabled"):
        return False
    words = str(player_message or "").strip().strip('"“”')
    if not re.match(r"^I\s+(?:choose|decide|will)\s+to\s+(?:leave\s+(?:the\s+house\s+)?|move\s+out\s+)alone\b",
                    words, re.I):
        return False
    model.romance_outcome = "solo_departure"
    model.world.add_event(model.world.minute, model.player_place(), (PLAYER,),
                          "The player chose to leave the house alone", kind="solo_ending",
                          operation_id=f"romance:solo:{model.turn}")
    model.world.remove(PLAYER)
    return True
