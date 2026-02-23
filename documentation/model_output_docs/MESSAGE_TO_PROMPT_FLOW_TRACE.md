# Message → Prompt Flow Trace (Current Code Path)

This document traces the exact runtime path from one completed LLM response to the next outgoing LLM request.

## 0) Starting Point: Prior LLM Response Exists
At the end of the prior turn, `prompt_engine.py` has already:
- stripped `[[STATE]]...[[/STATE]]` via `extract_state_tag`,
- applied state deltas with `apply_state_tag`,
- appended user/assistant messages to session log,
- optionally executed post-reply `KnowledgeResolutionExtractor` and wrote updates into:
  - belief graph (`state.beliefs[main_character_id].claims`),
  - transient buffer entries (`meta.source=knowledge_resolution`, TTL 8 turns).

This means the next turn starts from a state that may already include newly resolved knowledge ownership.

---

## 1) Request Intake
Endpoint: `POST /api/chat` → `backend/app/api/prompt_engine.py::chat_handler`

1. Parse `session_id` and message string.
2. Strip UI quote prefix (`>`).
3. Load session (`get_session`) and state/log references.
4. Sync epistemic feature gate with session toggle (`set_master`).
5. Handle early-return commands first: `[D]`, `[C]`, `[M]`, `[T]`, `[ES]`, `__cmd_reset__`, `__cmd_newgame__`.

If no early return, continue to regular turn path.

---

## 2) Regular Turn Preprocessing
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

## 3) Retrieval (FAISS + BM25)
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

Returned chunks are candidate memory fragments for both prompt construction and epistemic resolution.

---

## 4) Location Extraction (Pre-Render Extractor)
1. If world runtime exists and current location is known:
   - run `LocationExtractor.extract(...)` with:
     - user message,
     - world graph locations,
     - retrieved chunks (for disambiguation),
     - recent conversation log.
2. If extractor yields a valid move destination:
   - canonicalize message to `go to <destination_id>`.
3. Fallback heuristic can also convert message to movement command.
4. `advance_time(state, msg)` executes travel/time updates and world graph movement.

---

## 5) Transient Buffer Write (Conversation Echo)
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

## 6) Prompt Build Input Assembly
Create `PromptInput` with:
- current `state`,
- trimmed `log`,
- canonicalized user message,
- retrieved chunks,
- truth mode toggle,
- retrieval debug payload.

Then call `build_messages(prompt_input, return_debug=True)`.

---

## 7) System Prompt Construction (`prompt_builder.py`)
`system_prompt(...)` composes:
1. Base behavior/style rules.
2. Epistemic knowledge stack (`_format_labeled_knowledge_stack`):
   - `CANONICAL_CORE`: character basics + canonical facts,
   - `CANONICAL_GRAPH`: current place info,
   - `SUBJECTIVE_BELIEF`: belief claims for active speaker,
   - `RETRIEVED_MEMORY`: FAISS/BM25 chunks.
3. Relationship section (`character_graph.format_for_prompt`).
4. Scene brief includes explicit per-turn scene context:
   - `people_present` list and count,
   - `speakers` list.
5. Optional truth-mode override.

Important current rule in preface:
- If chunk visibility is not explicit for speaker, model should make best reasonable determination; hedge when uncertain.

---

## 8) User Message Header + Final Message List
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

## 9) Outbound LLM Call
`prompt_engine.py` builds payload with:
- model,
- messages,
- temperature,
- max tokens,
then sends to OpenAI Chat Completions.

This is the exact point where the new prompt is sent.

---

## 10) Post-Response Mutation Pipeline
After receiving response:
1. Extract and apply `[[STATE]]`.
2. Append final user/assistant text to log.
3. Add transient entry: `NPC replied: ...` (TTL = `TRANSIENT_KNOWLEDGE_TURNS`).
4. Evaluate win condition.
5. Run post-reply knowledge resolution for unknown chunks:
   - derive unknown candidate chunks from retrieval + canonical visibility checks,
   - run `KnowledgeResolutionExtractor` over last ~8 turns + latest exchange,
   - apply updates into belief graph (`kr::<speaker>::<chunk_id>` claims),
   - add transient knowledge objects with TTL 8 turns.
6. Upsert scene knowledge FIFO object:
   - location_id from previous-reply location extractor,
   - current-turn `speakers`,
   - current `people_present`,
   - payload metadata including location-change flag.

Result can include `knowledge_resolution_updates` for debug/inspection.

---

## 11) Where Each Graph/Store Is Used
- Character graph: prompt relationship section, rel delta mapping.
- Belief graph: seeded beliefs + post-reply knowledge resolution updates.
- World/place graph: movement extraction target set + travel + prompt location context.
- FAISS/BM25: retrieval slice for prompt and unknown-chunk candidates.
- Transient buffer:
   - conversation flavor (8-turn TTL),
  - resolved knowledge objects (8-turn TTL).
- Scene knowledge FIFO:
   - bounded to 8 entries,
   - refreshed on upsert by key,
   - used for previous-turn speaker carryover when location is unchanged.

---

## 12) Expiration / Cleanup Behavior
- Cleanup trigger: each turn start (`state.purge_transient_entries`).
- Knowledge-resolution objects naturally disappear after 8 turns unless refreshed by later extractor updates.
- Location-scoped transients are cleared on travel by gameplay flow.
- Scene knowledge objects are retained as FIFO queue items (max 8), not per-object countdown.
