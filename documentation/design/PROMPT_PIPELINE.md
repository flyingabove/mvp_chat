# Prompt pipeline: storyteller prompt, turn extractor, message flow, layer coverage

> This file merges several design documents (each keeps its own section, with its original status notes). Open work is in [../BACKLOG.md](../BACKLOG.md).

## Storyteller Prompt Redesign (Plain-English, Scene-Based)

> **What this doc is for:** Design of the narrative LLM prompt (Call 2 of the two-call turn). Edit this doc when the storyteller system prompt structure or injection order changes.

### Implementation status (2026-02-13)

- Phase A is implemented in `backend/app/engine/prompt_builder.py`:
   - paragraph-first storyteller contract
   - deterministic scene brief section
   - multi-character cast-pressure framing with main-character focus
   - relationship context reframed as scene tension guidance
- Critical intent guard removed — identity correction is now handled generically by the epistemic stack and factual integrity rules in the prompt contract, not per-story band-aids.
- All numeric relationship values replaced with deterministic word mappings (see "Relationship Word Mappings" section below).
- Context-aware character graph filtering implemented: only characters in current-turn mention scope, scene co-presence, or active phone-call scope are included in the prompt via transient markers in `active_characters.py`.
- Prompt scene brief now explicitly injects both `speakers` and `people_present` (including people count) before generation.
- Previous-turn speaker carry-over is applied only when location is unchanged (from scene knowledge FIFO).
- Extraction pipeline policy: one extractor LLM call per turn (`TurnExtractor`) with strict JSON output.

Remaining phases (validator/rewrite pass and full scorer rubric migration) are still pending.

### Why this redesign is needed

The current prompt is structurally strong but too instruction-heavy and speaker-constrained. It pushes the model into a "single-character chatbot" posture, which creates two recurring issues:

1. **Identity drift under pressure** (example: IU answering "previous tenant" as if that person were separate from IU).
2. **Narrow conversational framing** where the model only "acts as the main character" instead of narrating a living scene with multiple involved characters.

From the provided turn context:
- Canon clearly states IU is the prior tenant and died in the closet.
- The model still produced third-person rumor language ("they say she died...").

Root cause is not missing data; it is **prompt framing and instruction priority shape**.

---

### Product direction

Shift from a chatbot-style prompt to a **storytelling engine prompt**:

- The model narrates the current scene in plain-English prose.
- The main character remains the focal lens, but the model can include other relevant characters in the scene/world context.
- Dialogue remains embedded in narrative, not rigid Q&A voice only.
- Canonical truth remains enforced by the epistemic stack.

This is a narrative game, not just an NPC chat widget.

---

### Design goals

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

### Non-goals

- Replacing epistemic stack architecture.
- Removing deterministic state updates.
- Turning output into omniscient author narration that ignores character knowledge limits.

---

### Proposed prompt architecture (paragraph-first)

Replace many fragmented command-style blocks with 6 prose sections in this order:

#### 1) Scene Framing Paragraph
Short paragraph describing where/when we are, who is in focus, and emotional pressure in the moment.

#### 2) Narrative Contract Paragraph
Explain that the model is writing the next beat of an interactive story:
- cinematic narration + embedded dialogue
- no player action control
- maintain continuity and momentum

#### 3) Character Lens Paragraph (main focus)
Describe the main character's internal and outward stance, with explicit identity anchors in plain language.

#### 4) Cast & Tension Paragraph
Describe other relevant characters and relationships that can color response tone (suspicion, fear, trust, leverage).

#### 5) Truth & Knowledge Paragraph
Plain-English summary of what is canonically true, what is uncertain, and what must not be contradicted.

#### 6) Context Routing Paragraph (high-priority)
Describe who is currently in-scene, on-call, or actively mentioned so narrative focus stays local and does not drag in stale off-screen characters.

Current runtime contract:
- `people_present`: world-location presence (world graph location + character location index)
- `speakers`: current-turn speaking cast
- If location is unchanged, prior-turn speakers are eligible carry-over into current cast list
- Phone-call edge cases are deferred for now by product decision
- **Focal-lens framing is conditional for lifecycle-enabled stories** (2026-09-19
  fix, see `SIX_STRANGERS_AUDIT_PROPOSAL_2026_09_19.md (removed; see git history)`):
  `_storyteller_scene_section` and `_character_identity_section` in
  `prompt_builder.py` only frame the main character as "the focal lens" (and
  inject their identity block) when `_main_character_scene_eligible(state)`
  is true — for a lifecycle-enabled story (`state.cast_lifecycle.enabled`),
  that requires the main character to actually be in `people_present` for the
  current scene. When absent, the scene brief instead states plainly that the
  main character is not present and must not appear/speak/join uninvited.
  Non-lifecycle stories are unaffected (always eligible, unchanged legacy
  behavior — supports an always-present ghost/narrator NPC). This closes the
  bug where an explicit solitary scene still had the main NPC narrated in.

---

### Output behavior specification (Storyteller Mode)

#### Baseline behavior
- Output should read like a short story beat (1-4 compact paragraphs typically).
- Main character stays central, but other characters may be referenced naturally when relevant.
- Dialogue is woven into scene prose.

#### Multi-character handling
- If only one character is present, keep tight focus.
- If multiple characters are relevant, narration may include their pressure/influence, but should not flatten POV into omniscient certainty.
- Do not break epistemic limits: only reveal what active perspective could reasonably express.

#### Player-agency safety
- Continue prohibiting narration of player decisions/thoughts/body actions.
- The narrative can describe atmosphere and NPC behavior around the player.

#### State tag continuity
- `[[STATE]]` tags remain supported by the runtime parser, but the prompt no longer forces a mandatory terminal state line.

---

### Identity handling policy (soft, non-forced)

Identity-sensitive prompts should be handled through canon-first continuity and uncertainty-aware storytelling, not brittle per-story hard guards.

Preferred behavior:
- Prioritize canonical facts when identity is directly questioned.
- Allow emotional hesitation, but avoid drifting into contradictory third-person fabrication.
- Keep responses in narrative voice without forcing a fixed sentence template.

---

### Relationship Word Mappings (deterministic)

All numeric relationship values are converted to human-readable words before entering the prompt.
No raw numbers appear in the prompt — only these words.

Source code: `backend/app/engine/character_graph.py` (module-level dicts `_TRUST_WORDS`, `_AFFECTION_WORDS`, `_FEAR_WORDS`, `_SUSPICION_WORDS`).

TTL for transient buffer entries: `TRANSIENT_KNOWLEDGE_TURNS = 8` in `backend/app/config/settings.py`.

Each dimension maps 21 values from -1.0 to +1.0 in 0.1 increments. Fear and suspicion are stored as 0.0–1.0 internally but normalized to -1.0–+1.0 for word lookup.

#### Trust (-1.0 to +1.0)

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

#### Affection (-1.0 to +1.0)

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

#### Fear (normalized -1.0 to +1.0; stored internally as 0.0–1.0)

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

#### Suspicion (normalized -1.0 to +1.0; stored internally as 0.0–1.0)

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

#### Belief Certainty (0.0 to 1.0)

Belief confidence is stored on `KnowledgeChunk.confidence` (for chunks with `kind='claim'`) in the range 0.0–1.0.
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

#### Behavior Stance (composite, deterministic)

In addition to individual dimension words, a single **behavior tendency** sentence is generated from the combination of all four dimensions. Rules (evaluated in order, first match wins):

1. **Cooperative**: trust ≥ 0.3 AND affection ≥ 0.2 AND fear ≤ 0.1 AND suspicion ≤ 0.1 → "cooperative and candid, likely to engage and share"
2. **Defensive-hostile**: (trust ≤ -0.4 AND affection ≤ -0.4) AND (fear ≥ 0.3 OR suspicion ≥ 0.3) → "defensive-hostile, likely to resist, deflect, or confront"
3. **Hostile**: trust ≤ -0.4 AND affection ≤ -0.4 → "hostile distance, likely to push back and withhold"
4. **Defensive**: fear ≥ 0.3 OR suspicion ≥ 0.3 → "guarded defense, likely to hedge and reveal selectively"
5. **Default**: → "neutral-watchful, likely to respond cautiously without full openness"

#### Prompt output format

Each relationship renders as prose in the relationship context section, for example:
```
1. IU currently reads the player with neutral trust, guarded fear, neutral affection, and guarded suspicion. The relationship type is other. Neutral-watchful, likely to respond cautiously without full openness.
2. IU currently reads Han Jae-seo with skeptical trust, shaken fear, aloof affection, and convinced suspicion. This is an employer relationship with a clear boss-to-subordinate power dynamic. Defensive-hostile, likely to resist, deflect, or confront.
```

No numeric values appear anywhere in the prompt.

Runtime note:
- Relationship wording is rendered as natural prose with humanized tokens (for example, `highly_suspicious` becomes "highly suspicious").
- Role context is included in sentence form so power dynamics and relationship type are explicit without telemetry-style formatting.

---

### Epistemic Knowledge Stack — Prose Rendering Rules

The knowledge stack is rendered as plain-English numbered prose instead of machine-readable tags. All rendering logic lives in `backend/app/engine/prompt_builder.py`.

#### Character identity chunk

The main character entry renders as a natural sentence:
```
IU is a ghost in this story.
```
Source: `_knowledge_chunks_from_state()` — uses `f"{name} is a {role} in this story."`.

#### Tier headings

Each tier gets a prose heading instead of a `### TIER_NAME` header:

| Tier | Heading |
|------|---------|
| `CANONICAL_CORE` | "These are the definitive canonical facts of this story:" |
| `CANONICAL_GRAPH` | "World context relevant to the current scene:" |
| `SUBJECTIVE_BELIEF` | "Beliefs and suspicions (not necessarily true):" |
| `RETRIEVED_MEMORY` | "Remembered details from past interactions:" |

Source: `_TIER_HEADINGS` dict in `prompt_builder.py`.

#### Visibility prose rules

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
- Known character key → `Character.name` (e.g. `"iu"` → `"IU"`)
- Unknown key fallback → `key.replace("_", " ").title()` (e.g. `"rival_trainee"` → `"Rival Trainee"`)

#### Preface instructions

The stack preface tells the model how to use the facts:

> "The following sections describe what is true in this story and who knows what. Earlier sections outrank later sections when facts conflict. Each fact includes a plain-English note about which characters know it, do not know it, or may be partially aware of it."
>
> "When a fact says a character does not know something, that character must not state, hint at, or act on that information. When a fact says everyone knows something, treat it as common knowledge. When uncertain about whether a character would know a detail not listed here, hedge naturally instead of asserting certainty. Never state as fact anything the active speaker does not know."

#### Full example output

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

World context relevant to the current scene:
1. Current place=IU’s Apartment; description=A quiet, carefully kept apartment filled with muted light and personal belongings. Everyone knows this.

### RELATIONSHIP CONTEXT IN THIS SCENE

1. IU currently reads the player with neutral trust, guarded fear, neutral affection, and guarded suspicion. The relationship type is other. Neutral-watchful, likely to respond cautiously without full openness.
```

---

### Implementation status

#### Implemented
1. Prompt sections use prose-oriented epistemic headings and visibility language.
2. Relationship context is rendered once in scene prose with deterministic relationship words.
3. Active-character scope is constrained to current-turn mentions, same-location speakers, and active on-call markers.

#### Not implemented in runtime
1. No dedicated post-response rewrite validator pass is currently wired in runtime.
2. Evaluation/rubric changes remain owned by scorer/integration evolution, not this prompt composer module.

---

### Risks and mitigations

#### Risk: prose sections become vague
Mitigation: keep explicit, short constraints inside each paragraph and preserve hard guard paragraph.

#### Risk: model over-narrates and slows interaction
Mitigation: token cap + explicit "compact beat" instruction (1-4 paragraphs).

#### Risk: multi-character narration leaks unknown info
Mitigation: keep epistemic visibility suffix logic and unknown-handling rule in the truth paragraph.

---

### Success criteria

1. Responses feel like interactive narrative beats, not rigid chatbot turns.
2. Main character remains clear focal lens while scene context can include other relevant characters.
3. No regressions on agency rule, canonical consistency, and state-tag compliance.

---

### Simple example of the new style (illustrative)

"The apartment settles into a tense quiet as IU's eyes drift toward the closet door. She doesn't dodge this time.\n\n
\"You're asking about me,\" she says, voice low but steady. \"I was the previous tenant. I died in that closet.\"\n\n
The words hang between you, and the room seems to shrink around them as she studies your reaction."

This keeps narrative tone, identity truth, and player agency constraints at once.

---

## Single-Call Turn Extractor Design (Canonical)

> **What this doc is for:** Design of the state-extraction LLM call (Call 1 of the two-call turn). Edit this doc when the extractor schema, prompt, or validation logic changes.

### Purpose
Lock extractor architecture to one LLM extractor call per regular turn.

### Load When
- You are changing extraction behavior.
- You are investigating extraction latency/cost.
- You are validating extractor JSON parse/validation behavior.

### Canonical Code
- `backend/app/engine/extractors/turn_extractor.py`
- `backend/app/api/prompt_engine.py`
- `tests/backend/app/api/test_prompt_engine.py`

### Goal
Guarantee **exactly one extractor LLM call per regular turn** in the prompt engine, with strict JSON output that is easy to parse and validate.

### Non-Negotiable Rule
- The prompt engine must call **only** `TurnExtractor.extract(...)` once per turn.
- No additional location-classifier extractor call.
- No additional post-reply knowledge-resolution extractor call in the same turn.

### Why
- Prevent accidental latency/cost regressions from multi-extractor pipelines.
- Keep behavior deterministic and auditable.
- Enforce one schema and one integration point for extraction mutations.

### Extractor Input (Single Call)
The single extractor receives:
- current user message,
- world locations (id -> name),
- character map (key -> name),
- previous-turn user message,
- previous-turn assistant reply,
- previous-turn unknown candidate chunks,
- bounded conversation history.

### Extractor Output Schema (JSON)
```json
{
  "movement": {
    "intent": "MOVE|NONE",
    "destination_id": "string|null",
    "confidence": 0.0,
    "destination_text": "string"
  },
  "previous_scene": {
    "location_id": "string|null",
    "speakers": ["character_key"]
  },
  "knowledge_updates": [
    {
      "chunk_id": "string",
      "knows": true,
      "confidence": 0.0,
      "reason": "string"
    }
  ]
}
```

### Engine Application Rules
1. Apply `movement` pre-render using a separate `go to <destination_id>` input if valid. Preserve the full player text for the storyteller, history, and next-turn extraction.
2. Apply `previous_scene` into scene FIFO (`scene_knowledge_entries`).
3. Apply `knowledge_updates` into belief graph + transient mirror entries.
4. Persist current turn artifacts (`last_turn_user_msg`, `last_turn_assistant_reply`, `last_turn_retrieved_chunks`) for next turn extraction.
5. After travel changes location, refresh destination scene presence before rendering, including an explicitly empty scene when appropriate. Do not carry the previous room's speakers or identity gates into the destination.

### Validation Rules
- `destination_id` must be in allowed world location ids; otherwise drop move.
- `previous_scene.speakers` must be allowed character keys.
- `knowledge_updates.chunk_id` must be in provided candidate list.
- Confidence values are clamped to `[0.0, 1.0]`.

### Relationship to Scene Presence
- `people_present` is computed from world graph location + character location index each turn.
- `speakers` come from extractor output for previous turn and carry into scene context when location is unchanged.

### Ownership
- Runtime implementation: `backend/app/engine/extractors/turn_extractor.py`
- Prompt-engine integration: `backend/app/api/prompt_engine.py`
- Flow trace: `documentation/design/PROMPT_PIPELINE.md`

---

## Message → Prompt Flow Trace (Current Code Path)

> **What this doc is for:** Step-by-step trace of how a user message becomes an LLM prompt. Edit this doc when the prompt assembly pipeline changes.

### Purpose
Provide a deterministic, code-aligned trace from incoming user message to outgoing renderer prompt.

### Load When
- You are debugging prompt assembly.
- You need to verify where extraction, retrieval, and state mutation happen.
- You need the exact runtime order for prompt engine changes.

### Canonical Code
- `backend/app/api/prompt_engine.py`
- `backend/app/engine/prompt_builder.py`
- `tests/backend/app/api/test_prompt_engine.py`

This document traces the exact runtime path from one completed LLM response to the next outgoing LLM request.

### 0) Starting Point: Prior LLM Response Exists
At the end of the prior turn, `prompt_engine.py` has already:
- stripped `[[STATE]]...[[/STATE]]` via `extract_state_tag`,
- applied state deltas with `apply_state_tag`,
- appended user/assistant messages to session log,
- persisted previous-turn extractor context:
   - previous user message,
   - previous assistant reply,
   - previous retrieved chunks.

This means the next turn starts from a state that may already include newly resolved knowledge ownership.

---

### 1) Request Intake
Endpoint: `POST /api/chat` → `backend/app/api/prompt_engine.py::chat_handler`

1. Parse `session_id` and message string.
2. Strip UI quote prefix (`>`).
3. Load session (`get_session`) and state/log references.
4. Sync epistemic feature gate with session toggle (`set_master`).
5. Handle early-return commands first: `[D]`, `[C]`, `[M]`, `[T]`, `[ES]`, `__cmd_reset__`, `__cmd_newgame__`.

If no early return, continue to regular turn path.

---

### 2) Regular Turn Preprocessing
1. Guard checks:
   - no active game -> error reply,
   - game over -> finished reply.
2. Purge expired transient entries (`state.purge_transient_entries`):
   - removes old transient objects by turn/minute TTL.
3. Scene presence bootstrap:
   - load latest scene knowledge object from FIFO queue,
   - compare previous location_id vs current location_id,
   - if unchanged, carry previous turn speakers into active-cast seed,
   - query world location + character location index to derive `people_present`.
4. Name handling:
   - confirm guessed name from prior turn,
   - extract user name phrases and update user state.

---

### 3) Retrieval (FAISS + BM25)
1. Route retrieval namespace:
   - activate character bundle (`IndexService.set_active_character(state.knowledge_character_id)`),
   - build namespace `<user>-<story>-<instance>`.
2. Call `retrieve_knowledge(msg, namespace=...)`.
3. Retrieval logic in `backend/app/knowledge/runtime/retrieve.py`:
   - load index bundle from `IndexService.get()`,
   - hybrid ranking:
     - BM25 lexical scores,
     - FAISS vector search,
     - reciprocal fusion,
   - namespace filtering,
   - return top chunks + debug metadata.

Returned chunks are candidate memory fragments for prompt construction and for the next turn's single-call extractor.

---

### 4) Single-Call Turn Extraction (Pre-Render)
1. If world runtime exists and current location is known:
   - run `TurnExtractor.extract(...)` once with:
     - current user message,
     - world locations + character key map,
     - previous-turn user message,
     - previous-turn assistant reply,
     - previous-turn unknown candidate chunks,
     - recent conversation log.
2. Extractor returns one strict JSON payload containing:
   - movement intent (`MOVE|NONE`) + destination_id,
   - previous-turn scene location_id,
   - previous-turn speakers,
   - previous-turn knowledge updates (`chunk_id/knows/confidence/reason`).
3. If extractor yields a valid move destination:
   - create a separate movement input, `go to <destination_id>`, for travel resolution only; preserve the complete player message.
4. Apply extracted previous-turn scene knowledge into FIFO scene buffer.
5. Apply extracted previous-turn knowledge updates into belief graph + transient mirror entries.
6. The fallback heuristic can populate the separate movement input if the extractor returns no move.
7. `advance_time` executes travel/time updates using that movement input (or the original message for a non-movement turn).
8. After a location change, refresh destination people-present and active-character markers and scene FIFO context before rendering. Clear prior-location speakers; an empty destination must not fall back to the previous room's occupants.

Movement normalization must never replace the player message in the storyteller
prompt, conversation echo, in-memory history, persisted transcript, fact
extraction, or `last_turn_user_msg`. A request such as “I return to the living
room and ask Makoto about baseball” must retain its question as well as move
the player. Destination characters' identity sections must be available on
that same turn, not one turn later.

---

### 5) Transient Buffer Write (Conversation Echo)
Before rendering:
- add transient entry: `Player said: ...`
- scope: `conversation`
- TTL: `TRANSIENT_KNOWLEDGE_TURNS`.

Scene markers updated before render:
- `__active_character_marker__:<key>`
- `__people_present_marker__:<key>`

After reply, scene speaker markers are updated:
- `__scene_speaker_marker__:<key>`

---

### 6) Prompt Build Input Assembly
Create `PromptInput` with:
- current `state`,
- trimmed `log`,
- complete player message (after request-intake cleanup, without replacing it with the travel command),
- retrieved chunks,
- truth mode toggle,
- retrieval debug payload.

Then call `build_messages(prompt_input, return_debug=True)`.

---

### 7) System Prompt Construction (`prompt_builder.py`)
`system_prompt(...)` composes:
1. Base behavior/style rules.
2. Optional mode-context layer (`_mode_context_section`, see `design/SOCIAL_ENGINE.md (social mode)`) — tone/setting prose for stories that declare a top-level `mode` object (e.g. `social_sim` ensemble games). Empty string (no-op) for any story without `mode`.
3. Epistemic knowledge stack (`_format_labeled_knowledge_stack`):
   - `CANONICAL_CORE`: character basics + canonical facts,
   - `CANONICAL_GRAPH`: current place info,
   - `SUBJECTIVE_BELIEF`: belief claims for active speaker,
   - `RETRIEVED_MEMORY`: FAISS/BM25 chunks.
4. Relationship section (`character_graph.format_for_prompt`).
5. Scene brief includes explicit per-turn scene context:
   - `people_present` list and count,
   - `speakers` list.
6. Character self-knowledge (`_character_identity_section` — per-character; main character's block is unconditional, other present characters' blocks are gated by scene presence, see `design/SOCIAL_ENGINE.md (social mode)` §5).
7. Optional truth-mode override.

Important current rule in preface:
- If chunk visibility is not explicit for speaker, model should make best reasonable determination; hedge when uncertain.

---

### 8) User Message Header + Final Message List
`build_messages` appends a final user message with runtime header:
- minute,
- location,
- emotion,
- relationship,
then raw user content.

The final payload includes:
- one system message,
- trimmed history window,
- one current user message.

---

### 9) Outbound LLM Call
`prompt_engine.py` builds payload with:
- model,
- messages,
- temperature,
- max tokens,
then sends to OpenAI Chat Completions.

This is the exact point where the new prompt is sent.

---

### 10) Post-Response Mutation Pipeline
After receiving response:
1. Extract and apply `[[STATE]]`.
2. Append final user/assistant text to log.
3. Add transient entry: `NPC replied: ...` (TTL = `TRANSIENT_KNOWLEDGE_TURNS`).
4. Evaluate win condition.
5. Persist this completed turn into extractor carryover fields:
   - `last_turn_user_msg`,
   - `last_turn_assistant_reply`,
   - `last_turn_retrieved_chunks`.

Result can include `knowledge_resolution_updates` for debug/inspection (applied from single-call extractor output).

---

### 11) Where Each Graph/Store Is Used
- Character graph: prompt relationship section, rel delta mapping.
- Belief graph: seeded beliefs + single-call turn extractor knowledge updates.
- World/place graph: movement extraction target set + travel + prompt location context.
- FAISS/BM25: retrieval slice for prompt and unknown-chunk candidates.
- Transient buffer:
   - conversation flavor (8-turn TTL),
  - resolved knowledge objects (8-turn TTL).
- Scene knowledge FIFO (replacement for TTL scene memory flow):
   - bounded to 8 entries,
   - refreshed on upsert by key,
   - used for previous-turn speaker carryover when location is unchanged.

---

### 12) Expiration / Cleanup Behavior
- Cleanup trigger: each turn start (`state.purge_transient_entries`).
- Knowledge-resolution mirror objects naturally disappear after 8 turns unless refreshed by later single-call extractor updates.
- Location-scoped transients are cleared on travel by gameplay flow.
- Scene knowledge objects are retained as FIFO queue items (max 8), not per-object countdown.

---

## Layer Coverage Mapping (IU Scenario)

> **What this doc is for:** Maps which prompt layers are tested by which tests. Edit this doc when new prompt layers are added or test coverage changes.

### Purpose
Map IU scenario segments to epistemic layers and identify which tests verify each layer.

### Load When
- You update epistemic layer toggles.
- You change IU scenario assertions.
- You need to confirm whether layer failures are expected.

### Canonical Files
- Scenario harness: `backend/app/integration_playback/scenarios/scenario_epistemic_iu.py`
- Toggle behavior tests: `tests/backend/app/config/test_epistemic_flags.py`
- Prompt engine orchestration tests: `tests/backend/app/api/test_prompt_engine.py`

### Layer to Segment Mapping
- Truth layer: confession and disposal segments that become canonical facts.
- Belief layer: denials/contradictions that remain character-local claims until resolved.
- Narrative layer: visible scene output/flow steps in playback traces.
- Retrieval layer: retrieved snippets and memory blocks used for non-authoritative support.
- Mode-context layer (`_mode_context_section` in `prompt_builder.py`): optional tone/setting layer for the story-level `mode` object (e.g. `social_sim` ensemble games — see `design/SOCIAL_ENGINE.md (social mode)`). Emits nothing when `mode` is absent, so it never affects mystery-genre stories.

### Test Alignment
- `scenario_epistemic_iu` validates canonical facts, claims, and observations.
- `test_epistemic_flags` toggles master/per-layer gates and asserts expected pass/fail behavior.
- `test_prompt_engine` validates turn orchestration and prompt-layer assembly behavior.
- `test_prompt_builder.py::test_mode_context_section_*` validates the mode-context layer: absent for stories without `mode`, byte-identical prompt output for a pre-existing story (backward compatibility), and correct content (including the confessional convention) when `mode` is present.

### Maintenance Rules
- Update this mapping when scenario step order or toggle semantics change.
- Keep paths aligned with canonical source-mirrored test naming.
