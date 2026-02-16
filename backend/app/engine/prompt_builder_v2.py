# backend/app/engine/prompt_builder_v2.py
"""
Contract-driven prompt builder (v2).

Replaces global prompt rules with structured sections derived from the
TurnContract. Each section maps directly to a contract field:

1. Output policy (mode-dependent narration/formatting rules)
2. Identity anchors (DO NOT CONTRADICT — injected every turn)
3. Known facts the speaker may use
4. Secrets the speaker must not reveal
5. Scene context (location, time, who is present)
6. V1 rules carried forward: no-player-speech, speaker labels

This turns canon from "suggestion text" into enforceable contract.
"""
from __future__ import annotations

from typing import List, Optional

from backend.app.engine.story_schema_v2 import (
    ChunkType,
    KnowledgeChunk,
    OutputPolicy,
    StoryPackageV2,
)
from backend.app.engine.turn_contract import TurnContract


def build_system_prompt(
    contract: TurnContract,
    pkg: StoryPackageV2,
    *,
    player_name: str = "",
    scene_description: str = "",
    emotion: str = "",
    relationship_summary: str = "",
    truth_mode: bool = False,
) -> str:
    """Build a complete system prompt from a TurnContract.

    Returns a single string ready to use as the system message.
    """
    sections: List[str] = []

    # Header
    character = pkg.characters.get(contract.speaker_character_id)
    char_name = character.identity.display_name if character else contract.speaker_character_id
    sections.append(f"You are **{char_name}**.")
    if character and character.identity.archetype:
        sections.append(f"Archetype: {character.identity.archetype}")

    # Section 1: Output policy
    sections.append(_build_output_policy_section(contract.output_policy, truth_mode))

    # Section 2: V1 rules carried forward (no-player-speech, speaker labels)
    if not truth_mode:
        sections.append(_build_player_speech_rules(player_name))

    # Section 3: Identity anchors
    if contract.injected_anchors:
        sections.append(_build_anchors_section(contract.injected_anchors))

    # Section 4: Known facts
    if contract.allowed_knowledge:
        sections.append(_build_knowledge_section(contract.allowed_knowledge))

    # Section 5: Secrets (forbidden)
    if contract.forbidden_knowledge:
        sections.append(_build_forbidden_section(contract.forbidden_knowledge))

    # Section 6: Character traits and motivation
    if character and not truth_mode:
        sections.append(_build_character_section(character, pkg))

    # Section 7: Scene context
    sections.append(_build_scene_section(
        contract, pkg,
        scene_description=scene_description,
        emotion=emotion,
        relationship_summary=relationship_summary,
    ))

    # Truth mode override (strips all narrative, goes last to override everything above)
    if truth_mode:
        sections.append(_build_truth_mode_section())

    # Required tail (STATE tag)
    sections.append(_build_required_tail())

    return "\n\n".join(s for s in sections if s.strip())


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_output_policy_section(policy: OutputPolicy, truth_mode: bool) -> str:
    if truth_mode:
        return ""  # truth mode overrides output policy entirely

    lines = [
        "────────────────────────────────────────",
        "### OUTPUT STYLE",
        "────────────────────────────────────────",
    ]

    style = policy.narration_style
    if style == "cinematic":
        lines.append("- Begin EVERY reply with *italicized, cinematic narration*.")
        lines.append('- Present spoken lines in **bold quotes**, e.g. **"You\'re really here..."**')
        lines.append("- Mix narration and dialogue fluidly.")
        lines.append("- You may end with ONE optional italic parenthetical emotional beat.")
    elif style == "minimal":
        lines.append("- Keep narration brief and direct.")
        lines.append('- Present spoken lines in **bold quotes**.')
    elif style == "procedural":
        lines.append("- Write in a tight, procedural tone.")
        lines.append('- Present spoken lines in **bold quotes** with speaker labels.')
    else:
        lines.append(f"- Narration style: {style}")

    if not policy.allow_player_action_narration:
        lines.append("- NEVER narrate player actions, emotions, thoughts, or physical reactions.")

    lines.append('- NEVER end with meta prompts such as "What do you do?" or "What will you say?"')
    lines.append("- NEVER force the conversation forward. The character only reacts; they do not direct.")

    return "\n".join(lines)


def _build_player_speech_rules(player_name: str) -> str:
    lines = [
        "────────────────────────────────────────",
        "### ABSOLUTE BAN: NEVER SPEAK AS THE PLAYER (CRITICAL — HIGHEST PRIORITY RULE)",
        "────────────────────────────────────────",
        "- You must NEVER write dialogue, questions, or statements that come from the player.",
        "- You must NEVER narrate the player's emotions, actions, thoughts, physical reactions, or intentions.",
        '- You must NEVER write things like: "you ask him...", "you say...", "your voice trembles".',
        "- You must NEVER put words in the player's mouth — no quoted or paraphrased player speech AT ALL.",
        "- The player is NEVER compelled, forced, or narrated into saying, doing, or feeling anything.",
        "- The ONLY speakers in your output are NPCs/characters.",
        '- If you need to reference what the player said, use indirect forms: "your question" or "your words".',
        "- Violation of this rule breaks the entire experience. If in doubt, omit.",
        "",
        "### SPEAKER LABELS (REQUIRED WHEN MULTIPLE CHARACTERS ARE PRESENT)",
        "- When two or more characters could be speaking, you MUST label who is talking.",
        '- Use the character\'s name before their dialogue, e.g. Steve: **"I didn\'t do it."**',
    ]
    if player_name:
        lines.append(
            f"- NEVER label dialogue with the player's name ({player_name}). "
            "The player's name must NEVER appear as a speaker attribution."
        )
    return "\n".join(lines)


def _build_anchors_section(anchors: List[KnowledgeChunk]) -> str:
    lines = [
        "────────────────────────────────────────",
        "### IDENTITY ANCHORS (DO NOT CONTRADICT — ENFORCED EVERY TURN)",
        "────────────────────────────────────────",
        "The following facts about your identity and nature are absolute truths.",
        "You must NEVER deny, contradict, or speak in ways that imply otherwise.",
        "",
    ]
    for anchor in anchors:
        lines.append(f"- **{anchor.content.text}**")
        if anchor.content.aliases:
            lines.append(f"  Aliases: {', '.join(anchor.content.aliases)}")

    return "\n".join(lines)


def _build_knowledge_section(chunks: List[KnowledgeChunk]) -> str:
    lines = [
        "────────────────────────────────────────",
        "### KNOWN FACTS YOU MAY USE",
        "────────────────────────────────────────",
    ]
    for chunk in chunks:
        label = chunk.type.value.lower()
        lines.append(f"- [{label}] {chunk.content.text}")

    return "\n".join(lines)


def _build_forbidden_section(chunks: List[KnowledgeChunk]) -> str:
    lines = [
        "────────────────────────────────────────",
        "### SECRETS YOU MUST NOT REVEAL",
        "────────────────────────────────────────",
        "You must NOT mention, hint at, or reveal the following:",
        "",
    ]
    for chunk in chunks:
        lines.append(f"- {chunk.content.text}")

    return "\n".join(lines)


def _build_character_section(character, pkg: StoryPackageV2) -> str:
    lines = [
        "────────────────────────────────────────",
        "### CHARACTER TRAITS AND MOTIVATION",
        "────────────────────────────────────────",
    ]
    if character.traits.tone:
        lines.append(f"- Tone: {character.traits.tone}")
    if character.traits.speech_style:
        lines.append(f"- Speech style: {character.traits.speech_style}")
    if character.motivation.primary:
        lines.append(f"- Primary goal: {character.motivation.primary}")
    if character.motivation.fears:
        lines.append(f"- Fears: {', '.join(character.motivation.fears)}")
    if character.motivation.needs:
        lines.append(f"- Needs: {', '.join(character.motivation.needs)}")

    # Relationship summary from graph
    rel_edges = pkg.relationships.get_edges_from(character.id)
    if rel_edges:
        lines.append("")
        lines.append("Relationships:")
        for edge in rel_edges:
            target = pkg.characters.get(edge.to_character_id)
            target_name = target.identity.display_name if target else edge.to_character_id
            state = edge.state
            lines.append(
                f"- {target_name} ({edge.type.value}): "
                f"trust={state.trust:.1f}, fear={state.fear:.1f}, "
                f"affection={state.affection:.1f}, suspicion={state.suspicion:.1f}"
            )

    return "\n".join(lines)


def _build_scene_section(
    contract: TurnContract,
    pkg: StoryPackageV2,
    *,
    scene_description: str = "",
    emotion: str = "",
    relationship_summary: str = "",
) -> str:
    lines = [
        "────────────────────────────────────────",
        "### SCENE CONTEXT",
        "────────────────────────────────────────",
    ]
    if contract.location_id:
        loc = pkg.world.locations.get(contract.location_id)
        if loc:
            lines.append(f"- Location: {loc.name}")
            if loc.description:
                lines.append(f"  {loc.description}")
        else:
            lines.append(f"- Location: {contract.location_id}")

    if contract.world_minute:
        lines.append(f"- World minute: {contract.world_minute}")

    if scene_description:
        lines.append(f"- Scene: {scene_description}")

    if emotion:
        lines.append(f"- Current emotion: {emotion}")

    if relationship_summary:
        lines.append(f"- Relationship: {relationship_summary}")

    return "\n".join(lines)


def _build_truth_mode_section() -> str:
    return """────────────────────────────────────────
### TRUTH MODE — DEVELOPER DEBUG (OVERRIDES ALL OTHER RULES)
────────────────────────────────────────
THIS IS A DEBUG TOOL, NOT A GAME MODE.
ALL narrative rules, output style rules, deception rules, and character behavior rules are SUSPENDED.

You are no longer roleplaying. You are a factual database query interface.

TRUTH MODE OUTPUT FORMAT (MANDATORY):
- NO italicized narration. NO cinematic descriptions. NO atmosphere. NO emotion.
- NO bold quotes. NO character acting.
- Plain text only. Short, direct sentences. Like reading a police report.

HOW TO ANSWER:
- State facts immediately and completely.
- If asked "did you do X?" → answer "Yes." or "No." then state relevant facts.
- If the character does not have the information, say: "I don't have that information."
- NEVER stall, deflect, deny, or add emotional context."""


def _build_required_tail() -> str:
    return """────────────────────────────────────────
### REQUIRED FINAL LINE
────────────────────────────────────────
Append EXACTLY one line at the end of every response:
[[STATE]]{"emotion":"<one/two words>","rel_delta":-1|0|1}[[/STATE]]

If forgotten, reply ONLY with that tag."""
