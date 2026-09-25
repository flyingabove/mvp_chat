"""The only way world-model data reaches the storyteller: one prompt section
plus one header line, formatted from the per-turn TurnView (already filtered:
present, eligible, perceivable, and each speaker's OWN memories only)."""
from __future__ import annotations

from backend.app.engine.world_model.model import TurnView

RULE = "────────────────────────────────────────"
ENDING_KINDS = ("question", "offer", "action", "quiet")


def _names(view: TurnView, ids: list[str]) -> str:
    return ", ".join(view.names.get(i, i) for i in ids)


def render_scene_section(view: TurnView) -> str:
    if view.allowed_speakers is None:
        return ""
    lines = [f"\n{RULE}\n### WORLD STATE (engine-authoritative, overrides guesses)\n{RULE}"]
    if view.time_text:
        lines.append(f"Time: {view.time_text}.")
    if view.cards:
        lines.append("People with the player right now (location, activity and state are facts):")
        lines.extend(f"- {card}" for card in view.cards)
    else:
        lines.append("Nobody else is physically with the player right now: write narration only; no character "
                     "speaks unless they are on a call with the player. Voices from other rooms stay muffled and "
                     "unattributed.")
    if view.elsewhere:
        lines.append("Elsewhere (not visible to the player; answer 'where is X' from this only if the speaker "
                     "would plausibly know):")
        lines.extend(f"- {item}" for item in view.elsewhere)
    if view.transitions:
        lines.append("Just happened in view of the player (narrate briefly, as observed):")
        lines.extend(f"- {t}" for t in view.transitions)
    if view.traces:
        lines.append("Noticeable signs of what happened while the player was not watching (show through behavior "
                     "or detail, never as a report; nobody explains what they did not witness):")
        lines.extend(f"- {t}" for t in view.traces)
    if view.plan.speakers:
        plan = f"SPEAKER PLAN (engine-chosen; overrides pacing guidance about who speaks): {_names(view, view.plan.speakers)}"
        if view.plan.reason:
            plan += f" ({view.plan.reason})"
        plan += ". Only these characters have spoken lines this beat."
        if view.plan.silent_present:
            plan += f" {_names(view, view.plan.silent_present)} may react silently (a look, a gesture) but do not speak."
        if view.plan.initiative:
            plan += (f" {view.names.get(view.plan.initiative, view.plan.initiative)} may take one small initiative "
                     "of their own (a question, an offer, or a remark about their own life).")
        lines.append(plan)
    if view.perspectives:
        lines.append("What each speaker personally remembers that bears on this moment (their OWN memories; "
                     "they know nothing else about these topics):")
        for cid, memories in view.perspectives.items():
            for memory in memories:
                lines.append(f"- {view.names.get(cid, cid)}: {memory}")
    if view.must_address:
        lines.append("MUST ADDRESS THIS TURN (facts from the engine; include each naturally, invent nothing beyond them):")
        lines.extend(f"- {item}" for item in view.must_address)
    if view.ending_hint:
        lines.append(view.ending_hint)
    return "\n".join(lines) + "\n"


def render_header(view: TurnView) -> str:
    parts = []
    if view.plan.speakers:
        parts.append(f"Speakers this beat: {_names(view, view.plan.speakers)}.")
    if view.must_address:
        parts.append("Must address: " + " | ".join(view.must_address[:3]) + ".")
    return " ".join(parts)


def ending_hint(recent: list[str]) -> str:
    """Suggest an ending kind different from the last two (varied handoffs)."""
    avoid = set(recent[-2:])
    options = [k for k in ENDING_KINDS if k not in avoid]
    if not options or not recent:
        return ""
    descriptions = {"question": "a sincere question", "offer": "an offer or invitation",
                    "action": "an unfinished action the player can join", "quiet": "a comfortable pause"}
    return ("Ending: the last beats ended with " + " and ".join(dict.fromkeys(recent[-2:]))
            + "; end this one differently, e.g. with " + " or ".join(descriptions[o] for o in options[:2]) + ".")


def classify_ending(text: str) -> str:
    tail = (text or "").strip()[-160:].lower()
    if tail.endswith("?"):
        return "question"
    if any(w in tail for w in ("want to", "wanna", "join", "come with", "let's", "shall we", "how about")):
        return "offer"
    if tail.endswith(("...", "…")) or any(w in tail for w in ("reaches", "holds out", "hands", "starts to")):
        return "action"
    return "quiet"
