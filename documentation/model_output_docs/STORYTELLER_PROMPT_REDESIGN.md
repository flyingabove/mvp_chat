# Storyteller Prompt Redesign (Plain-English, Scene-Based)

## Implementation status (2026-02-13)

- Phase A is implemented in `backend/app/engine/prompt_builder.py`:
   - paragraph-first storyteller contract
   - deterministic scene brief section
   - multi-character cast-pressure framing with main-character focus
   - relationship context reframed as scene tension guidance
- Critical intent guard removed — identity correction is now handled generically by the epistemic stack and factual integrity rules in the prompt contract, not per-story band-aids.
- All numeric relationship values replaced with deterministic word mappings (see "Relationship Word Mappings" section below).
- Context-aware character graph filtering implemented: only characters mentioned in conversation or present at the scene are included in the prompt. Uses transient buffer TTL decay via `active_characters.py`.

Remaining phases (validator/rewrite pass and full scorer rubric migration) are still pending.

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

## Relationship Word Mappings (deterministic)

All numeric relationship values are converted to human-readable words before entering the prompt.
No raw numbers appear in the prompt — only these words.

Source code: `backend/app/engine/character_graph.py` (module-level dicts `_TRUST_WORDS`, `_AFFECTION_WORDS`, `_FEAR_WORDS`, `_SUSPICION_WORDS`).

TTL for transient buffer entries: `TRANSIENT_KNOWLEDGE_TURNS = 8` in `backend/app/config/settings.py`.

Each dimension maps 21 values from -1.0 to +1.0 in 0.1 increments. Fear and suspicion are stored as 0.0–1.0 internally but normalized to -1.0–+1.0 for word lookup.

### Trust (-1.0 to +1.0)

| Value | Word |
|-------|------|
| -1.0 | betrayed |
| -0.9 | treacherous |
| -0.8 | hostile |
| -0.7 | distrustful |
| -0.6 | wary |
| -0.5 | skeptical |
| -0.4 | guarded |
| -0.3 | reserved |
| -0.2 | cautious |
| -0.1 | unsure |
| 0.0 | neutral |
| +0.1 | open |
| +0.2 | receptive |
| +0.3 | cooperative |
| +0.4 | confident |
| +0.5 | reliant |
| +0.6 | trusting |
| +0.7 | devoted |
| +0.8 | steadfast |
| +0.9 | unshakable |
| +1.0 | absolute |

### Affection (-1.0 to +1.0)

| Value | Word |
|-------|------|
| -1.0 | hateful |
| -0.9 | resentful |
| -0.8 | cold |
| -0.7 | bitter |
| -0.6 | hostile |
| -0.5 | distant |
| -0.4 | aloof |
| -0.3 | detached |
| -0.2 | dry |
| -0.1 | reserved |
| 0.0 | neutral |
| +0.1 | warm |
| +0.2 | friendly |
| +0.3 | fond |
| +0.4 | caring |
| +0.5 | attached |
| +0.6 | affectionate |
| +0.7 | devoted |
| +0.8 | tender |
| +0.9 | adoring |
| +1.0 | deeply_bonded |

### Fear (normalized -1.0 to +1.0; stored internally as 0.0–1.0)

| Value | Word |
|-------|------|
| -1.0 | fearless |
| -0.9 | calm |
| -0.8 | steady |
| -0.7 | composed |
| -0.6 | unfazed |
| -0.5 | alert |
| -0.4 | watchful |
| -0.3 | uneasy |
| -0.2 | nervous |
| -0.1 | tense |
| 0.0 | guarded |
| +0.1 | anxious |
| +0.2 | shaken |
| +0.3 | alarmed |
| +0.4 | frightened |
| +0.5 | panicked |
| +0.6 | terrified |
| +0.7 | horrified |
| +0.8 | petrified |
| +0.9 | overwhelmed |
| +1.0 | paralyzed |

### Suspicion (normalized -1.0 to +1.0; stored internally as 0.0–1.0)

| Value | Word |
|-------|------|
| -1.0 | fully_trusting |
| -0.9 | trusting |
| -0.8 | accepting |
| -0.7 | open-minded |
| -0.6 | unconcerned |
| -0.5 | relaxed |
| -0.4 | attentive |
| -0.3 | questioning |
| -0.2 | doubtful |
| -0.1 | uncertain |
| 0.0 | guarded |
| +0.1 | skeptical |
| +0.2 | wary |
| +0.3 | dubious |
| +0.4 | suspicious |
| +0.5 | highly_suspicious |
| +0.6 | convinced |
| +0.7 | accusatory |
| +0.8 | paranoid |
| +0.9 | hypervigilant |
| +1.0 | obsessed |

### Belief Certainty (0.0 to 1.0)

Belief confidence is stored on `EpistemicClaim.confidence` in the range 0.0–1.0.
Internally, that value is rounded to the nearest 0.1 and converted to a deterministic certainty label:

| Value | Word |
|-------|------|
| 0.0 | speculative |
| 0.1 | very_tentative |
| 0.2 | tentative |
| 0.3 | leaning_uncertain |
| 0.4 | uncertain |
| 0.5 | mixed |
| 0.6 | leaning_likely |
| 0.7 | plausible |
| 0.8 | likely |
| 0.9 | highly_likely |
| 1.0 | certain |

Prompt-facing output uses natural confidence buckets (derived from the deterministic label):

| Internal Labels | Prompt Phrase |
|----------------|---------------|
| `speculative`, `very_tentative` | with very low confidence |
| `tentative`, `leaning_uncertain`, `uncertain` | with low confidence |
| `mixed` | with mixed confidence |
| `leaning_likely`, `plausible` | with moderate confidence |
| `likely`, `highly_likely` | with high confidence |
| `certain` | with complete confidence |

Belief lines render with the natural confidence phrase in the visibility prefix, then the fact text:

```
Currently only IU knows this with low confidence: IU died the prior week in the Nonhyeon-dong officetel closet; she is now the ghost in the apartment.
```

### Behavior Stance (composite, deterministic)

In addition to individual dimension words, a single **behavior tendency** sentence is generated from the combination of all four dimensions. Rules (evaluated in order, first match wins):

1. **Cooperative**: trust ≥ 0.3 AND affection ≥ 0.2 AND fear ≤ 0.1 AND suspicion ≤ 0.1 → "cooperative and candid, likely to engage and share"
2. **Defensive-hostile**: (trust ≤ -0.4 AND affection ≤ -0.4) AND (fear ≥ 0.3 OR suspicion ≥ 0.3) → "defensive-hostile, likely to resist, deflect, or confront"
3. **Hostile**: trust ≤ -0.4 AND affection ≤ -0.4 → "hostile distance, likely to push back and withhold"
4. **Defensive**: fear ≥ 0.3 OR suspicion ≥ 0.3 → "guarded defense, likely to hedge and reveal selectively"
5. **Default**: → "neutral-watchful, likely to respond cautiously without full openness"

### Prompt output format

Each relationship renders as:
```
- The Player (player) (other): Trust is neutral; fear is guarded; affection is neutral; suspicion is guarded.
  Behavior tendency: neutral-watchful, likely to respond cautiously without full openness.
  [optional label context]
```

No numeric values appear anywhere in the prompt.

---

## Epistemic Knowledge Stack — Prose Rendering Rules

The knowledge stack is rendered as plain-English numbered prose instead of machine-readable tags. All rendering logic lives in `backend/app/engine/prompt_builder.py`.

### Character identity chunk

The main character entry renders as a natural sentence:
```
IU is a ghost in this story.
```
Source: `_knowledge_chunks_from_state()` — uses `f"{name} is a {role} in this story."`.

### Tier headings

Each tier gets a prose heading instead of a `### TIER_NAME` header:

| Tier | Heading |
|------|---------|
| `CANONICAL_CORE` | "These are the definitive canonical facts of this story:" |
| `CANONICAL_GRAPH` | "Relationship dynamics and world context:" |
| `SUBJECTIVE_BELIEF` | "Beliefs and suspicions (not necessarily true):" |
| `RETRIEVED_MEMORY` | "Remembered details from past interactions:" |

Source: `_TIER_HEADINGS` dict in `prompt_builder.py`.

### Visibility prose rules

Each fact's `known_by`, `not_known_by`, and `maybe_known_by` lists are converted to a plain-English suffix sentence by `_visibility_prose()`. The rules (evaluated in order):

| Scenario | Output |
|----------|--------|
| `known_by` contains `"all_characters"` | `"Everyone knows this."` |
| Single knower, no other lists | `"Currently only {name} knows this."` |
| Multiple knowers, no other lists | `"{names} know this."` |
| Knower(s) + not_known_by | `"{names} know(s) this but {names} do(es) not yet know."` |
| Only not_known_by (no knowers) | `"{names} do(es) not yet know this."` |
| maybe_known_by (appended to any above) | `"{names} may have some awareness of this."` |
| All lists empty | No suffix (empty string) |

**Verb agreement**: singular subject uses "knows"/"does not yet know", plural uses "know"/"do not yet know".

**Name conjunction** (`_english_join`):
- 1 name: `"IU"`
- 2 names: `"IU and the player"`
- 3+ names: `"IU, Han Jae-seo, and the player"` (Oxford comma)

**Name resolution** (`_resolve_name`):
- `"player"` → `"the player"`
- `"all_characters"` → `"everyone"`
- Known character key → `CharacterState.name` (e.g. `"iu"` → `"IU"`)
- Unknown key fallback → `key.replace("_", " ").title()` (e.g. `"rival_trainee"` → `"Rival Trainee"`)

### Preface instructions

The stack preface tells the model how to use the facts:

> "The following sections describe what is true in this story and who knows what. Earlier sections outrank later sections when facts conflict. Each fact includes a plain-English note about which characters know it, do not know it, or may be partially aware of it."
>
> "When a fact says a character does not know something, that character must not state, hint at, or act on that information. When a fact says everyone knows something, treat it as common knowledge. When uncertain about whether a character would know a detail not listed here, hedge naturally instead of asserting certainty. Never state as fact anything the active speaker does not know."

### Full example output

```
────────────────────────────────────────
### EPISTEMIC KNOWLEDGE STACK
────────────────────────────────────────
The following sections describe what is true in this story and who knows what...

These are the definitive canonical facts of this story:
1. IU is a ghost in this story. Currently only IU knows this.
2. IU died the prior week in the Nonhyeon-dong officetel closet; she is now the ghost in the apartment. IU knows this but the player does not yet know. Han Jae-seo, Park So-jin, Rival Trainee, and Yoo Min-ho may have some awareness of this.
3. A prior tenant death occurred in the unit and is now part of building rumor context. Everyone knows this.
4. The apartment's cheap rent was due to the undisclosed prior tenant death in the closet. The player and Park So-jin know this but Rival Trainee does not yet know. Han Jae-seo and Yoo Min-ho may have some awareness of this.

Relationship dynamics and world context:
1. iu->player type=other Trust is neutral; fear is guarded; affection is neutral; suspicion is guarded. IU and the player know this.
```

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
