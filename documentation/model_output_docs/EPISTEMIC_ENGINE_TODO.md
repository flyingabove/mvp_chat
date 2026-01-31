# Epistemic Engine To-Do (Aligned to North Star)

## 1) Clarifying Questions & Assumptions
- Decision: Two-call loop approved — one structured extractor (state mutation only, including movement, quests, claims/contradictions, rel/emotion, evidence; no prose) plus one narrative call; double-LLM cost per turn is accepted.
- Decision: Memory windows are short (MEMORY_TURNS=8, EXTRACTOR_TURNS=8); we will add a compact epistemic store (facts/claims) that survives log trimming.
- Decision: We will extend story JSON with triggers and incentives for epistemic reasoning; start with the provided IU integration test case, then later augment the live game with triggers after the mini-game proves out.
- Decision: Knowledge retrieval stays character-scoped (BM25+FAISS); we will reuse it for epistemic cues and add a lightweight per-story knowledge graph when needed without new infra.
- Decision: Difficulty modes, rerolls, and post-milestone loops from the north star are not yet wired; keep code changes compatible with the current single-mode flow.
- Decision: Chinese translation/debug/map toggles stay as-is; epistemic features must remain language-agnostic and keep [[STATE]] intact.

## 2) General Suggestions
- Enforce single ground truth: keep epistemic state alongside MurderGameState, never inside prompt text only.
- Make extractor schemas explicit: typed JSON for movements, claims, contradictions, and quest triggers to avoid prompt drift.
- Keep prompts lean: inject only canonical facts/claims with provenance so the model can say "unknown" safely.
- Prefer deterministic steps: seeded travel rules already exist—mirror that determinism in epistemic updates (e.g., rule-based merges before LLM speculation).
- Add instrumentation: log epistemic mutations (who said what, when, with confidence) for debugging and regression tests.

## 3) TODO Items (High-Level with Substeps)
- **Epistemic data model**: introduce dataclasses (e.g., `EpistemicFact`, `Claim`, `Observation`, `BeliefState`) with fields for `id`, `source` (npc/player/system), `timestamp_minute`, `confidence`, `location_ref`, `subject`/`object`, `status` (asserted, contested, resolved).
  - Provide helper methods: `record_observation(...)`, `contested_with(...)`, `resolve_conflict(...)`, `as_prompt_snippet()`.
  - Store on `MurderGameState` (e.g., `epistemic_log: list[Claim]`, `canonical_facts: list[EpistemicFact]`).
- **Extractor pass (call #1)**: add `EpistemicExtractor` module to classify turn content into structured updates (movement intent, claims, contradictions, quest triggers) using conversation window + knowledge hints.
  - Schema (enforce categories + provenance labels):
    - `moves`: [{`destination_id`, `via` (ids), `raw_text`}]
    - `claims`: [{`speaker`: player|npc, `content`, `subject`, `object`, `time_ref`, `location_ref`, `confidence`, `provenance`: observed|testimony|inferred|rumor}]
    - `quests`: [{`id`, `status`: triggered|progress|completed}]
    - `rel_emotion`: {`rel_delta`: -1|0|1, `emotion`}
    - `evidence`: [{`id`, `action`: add|remove, `note`, `confidence`, `provenance`}]
    - `world_mutations`: [{`type`: add|update|delete, `target`: location|item|flag, `id`, `fields`}] (optional, for non-move state changes)
  - Validation: reject/flag unknown locations unless `unknown_npc_X`/placeholder; block world mutations that violate graph; keep provenance so renderer can hedge.
- **State updater**: implement merge rules to apply extractor output into `MurderGameState`'s epistemic structures.
  - Deduplicate by normalized subject/object; bump confidence on repeats; mark contradictions when two claims disagree.
  - Attach minute/location from `advance_time` and `world_clock` for temporal ordering.
- **Narrative prompt lift (call #2)**: extend `prompt_builder` to include a short "What the world knows" block with resolved facts + contested claims (with speaker labels) instead of raw log replay.
  - Keep memory concise (age out low-confidence or stale claims; cap per subject).
  - Add explicit instruction: "Do not invent new facts; if not in epistemic log, say you don't know."
- **Story JSON extensions + IU mini-game**: add quest/trigger metadata first in the IU integration test harness, validate via the IU case, then port triggers into the main game stories after extractor/state updater are stable; build an IU "mini-game" scenario to exercise the full pipeline.
- **Character knowledge graph**: optional lightweight graph linking characters, locations, and evidence ids.
  - Structure: `CharacterNode`, `Edge(type="saw_at", "reported", "conflicts_with")` stored on state; helper `link(subject, edge_type, target, minute, confidence)`.
  - Use to cross-check hallucinated NPCs and merge aliases (e.g., nicknames vs canonical ids).
- **Testing & fixtures**: build deterministic scenarios using `EpistemicStateIUExample` narrative.
  - Unit: extractor JSON validity, merge rules, contradiction detection, prompt formatting, time ordering.
  - Integration: five-turn playthrough asserting epistemic log contains IU case facts (who confessed, cover-up items, contradictions logged).
- **Tooling & hooks**: add debug box subsection to show top claims/facts, and structured logging (`epistemic_event`) for each mutation.

## 5) Knowledge Graph Plan (truth vs belief vs retrieval)
- Layers and precedence: Truth graph/state (canonical) > Epistemic/belief graphs (per character + player observation log) > Narrative log (what was said) > Retrieval index (lowest authority, for phrasing only).
- Truth graph: locations, items/evidence, irreversible flags, validated world mutations. Updated only via validated extractor outputs + deterministic rules.
- Belief/observation: per-character belief graph plus player observation log for what was seen/heard/claimed; can diverge from truth.
- Retrieval: keep for style/backstory/dialogue; must be labeled (OBSERVED/TESTIMONY/RUMOR/INFERRED/NARRATION) and never overwrite truth.
- Conflict handling: if retrieval contradicts truth, downgrade to testimony/rumor in prompts; renderer hedges unless truth is observable to player.
- Tagging rule: before asserting a hard fact in prompts, ensure it is (a) observable truth or (b) an observation/evidence item; otherwise hedge as claim/belief.

## 4) Edge Cases to Plan For
- **Hallucinated NPCs**: when the LLM references an unknown person, create a temporary `npc_unknown_X` node with low confidence; never merge into canonical characters without explicit confirmation.
- **Name collisions/aliases**: handle "Steve" vs "Stephen" vs "he" by normalizing and linking aliases; avoid overwriting canonical ids.
- **Contradictory timelines**: two claims about the same time/location should mark a conflict flag; renderer should acknowledge uncertainty rather than pick a side.
- **Missing locations**: if extractor proposes a destination not in the world graph, drop the move but keep the claim as a verbal intent with a note.
- **Translation mode**: ensure Chinese translation wraps only the rendered text, not the internal [[STATE]] tag or epistemic log structures.
- **Session resets**: `__cmd_reset__` should clear epistemic data to avoid bleed between runs.
