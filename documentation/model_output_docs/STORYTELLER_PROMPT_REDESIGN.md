# Storyteller Prompt Redesign (Plain-English, Scene-Based)

## Why this redesign is needed

The current prompt is structurally strong but too instruction-heavy and speaker-constrained. It pushes the model into a "single-character chatbot" posture, which creates two recurring issues:

1. **Identity drift under pressure** (example: IU answering "previous tenant" as if that person were separate from IU).
2. **Narrow conversational framing** where the model only "acts as the main character" instead of narrating a living scene with multiple involved characters.

From the provided turn context:
- Canon clearly states IU is the prior tenant and died in the closet.
- The model still produced third-person rumor language ("they say she died...").

Root cause is not missing data; it is **prompt framing and instruction priority shape**.

---

## Product direction

Shift from a chatbot-style prompt to a **storytelling engine prompt**:

- The model narrates the current scene in plain-English prose.
- The main character remains the focal lens, but the model can include other relevant characters in the scene/world context.
- Dialogue remains embedded in narrative, not rigid Q&A voice only.
- Canonical truth remains enforced by the epistemic stack.

This is a narrative game, not just an NPC chat widget.

---

## Design goals

1. **Prompt readability for LLM**
   - Prefer paragraph sections with clear narrative intent over dense policy bullets.

2. **Storyteller output mode**
   - Model describes what is unfolding in-scene while centering the main character.

3. **Identity safety for critical intents**
   - Certain questions (like "previous tenant") require direct correction with first-person truth.

4. **Multi-character awareness**
   - Mention relevant secondary characters when useful to mystery progression, relationships, or stakes.

5. **Preserve existing engine guarantees**
   - No player action narration.
   - Canonical precedence remains intact.
   - Existing `[[STATE]]` tag contract remains intact during rollout.

---

## Non-goals

- Replacing epistemic stack architecture.
- Removing deterministic state updates.
- Turning output into omniscient author narration that ignores character knowledge limits.

---

## Proposed prompt architecture (paragraph-first)

Replace many fragmented command-style blocks with 6 prose sections in this order:

### 1) Scene Framing Paragraph
Short paragraph describing where/when we are, who is in focus, and emotional pressure in the moment.

### 2) Narrative Contract Paragraph
Explain that the model is writing the next beat of an interactive story:
- cinematic narration + embedded dialogue
- no player action control
- maintain continuity and momentum

### 3) Character Lens Paragraph (main focus)
Describe the main character's internal and outward stance, with explicit identity anchors in plain language.

### 4) Cast & Tension Paragraph
Describe other relevant characters and relationships that can color response tone (suspicion, fear, trust, leverage).

### 5) Truth & Knowledge Paragraph
Plain-English summary of what is canonically true, what is uncertain, and what must not be contradicted.

### 6) Intent Guard Paragraph (high-priority)
Small "if this intent appears, do X" prose for fragile intents.
Example guard for IU:
"If asked about the previous tenant or who died in the closet, IU must clarify directly that she herself was that tenant, in first person."

---

## Output behavior specification (Storyteller Mode)

### Baseline behavior
- Output should read like a short story beat (1-4 compact paragraphs typically).
- Main character stays central, but other characters may be referenced naturally when relevant.
- Dialogue is woven into scene prose.

### Multi-character handling
- If only one character is present, keep tight focus.
- If multiple characters are relevant, narration may include their pressure/influence, but should not flatten POV into omniscient certainty.
- Do not break epistemic limits: only reveal what active perspective could reasonably express.

### Player-agency safety
- Continue prohibiting narration of player decisions/thoughts/body actions.
- The narrative can describe atmosphere and NPC behavior around the player.

### State tag continuity
- Keep final `[[STATE]]` line until a later migration explicitly redesigns state extraction.

---

## Critical intent policy (Identity Correction)

For IU story family, add explicit semantic triggers in prompt-building:

Trigger phrases (normalized):
- "previous tenant"
- "who died in the closet"
- "what happened to the tenant"

Required response property:
- First-person identity correction within the same answer beat.

Acceptable examples:
- "I was the previous tenant. I died in that closet."
- "You're asking about me. I'm the one who was found there."

Disallowed pattern:
- Third-person distancing ("she died there") without immediate self-clarification.

---

## Implementation plan

### Phase A — Prompt builder refactor
1. Introduce paragraph-oriented section composer in `backend/app/engine/prompt_builder.py`.
2. Preserve epistemic ordering but summarize each tier into prose blocks.
3. Keep relationship context as prose influence, not list-like telemetry where possible.

### Phase B — Intent guard insertion
1. Add story/character-specific guard generator for fragile intents.
2. Inject only when trigger intent risk is present (or always for known fragile stories, as a first pass).

### Phase C — Output validator (lightweight)
1. Add post-response check for known identity-critical intents.
2. If violation detected, run a constrained rewrite pass (same content, corrected identity framing).

### Phase D — Evaluation updates
1. Update scorer rubric to score "story beat coherence" and "identity correction under implication".
2. Remove IU xfail quarantine only after repeated stable pass runs.

---

## Risks and mitigations

### Risk: prose sections become vague
Mitigation: keep explicit, short constraints inside each paragraph and preserve hard guard paragraph.

### Risk: model over-narrates and slows interaction
Mitigation: token cap + explicit "compact beat" instruction (1-4 paragraphs).

### Risk: multi-character narration leaks unknown info
Mitigation: keep epistemic visibility suffix logic and unknown-handling rule in the truth paragraph.

---

## Success criteria

1. IU "previous tenant" prompt yields direct first-person correction consistently.
2. Responses feel like interactive narrative beats, not rigid chatbot turns.
3. Main character remains clear focal lens while scene context can include other relevant characters.
4. No regressions on agency rule, canonical consistency, and state-tag compliance.

---

## Simple example of the new style (illustrative)

"The apartment settles into a tense quiet as IU's eyes drift toward the closet door. She doesn't dodge this time.\n\n
\"You're asking about me,\" she says, voice low but steady. \"I was the previous tenant. I died in that closet.\"\n\n
The words hang between you, and the room seems to shrink around them as she studies your reaction."

This keeps narrative tone, identity truth, and player agency constraints at once.
