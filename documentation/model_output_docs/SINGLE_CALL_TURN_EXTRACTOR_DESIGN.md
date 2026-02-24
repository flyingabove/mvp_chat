# Single-Call Turn Extractor Design (Canonical)

## Purpose
Lock extractor architecture to one LLM extractor call per regular turn.

## Load When
- You are changing extraction behavior.
- You are investigating extraction latency/cost.
- You are validating extractor JSON parse/validation behavior.

## Canonical Code
- `backend/app/engine/extractors/turn_extractor.py`
- `backend/app/api/prompt_engine.py`
- `tests/backend/app/api/test_prompt_engine.py`

## Goal
Guarantee **exactly one extractor LLM call per regular turn** in the prompt engine, with strict JSON output that is easy to parse and validate.

## Non-Negotiable Rule
- The prompt engine must call **only** `TurnExtractor.extract(...)` once per turn.
- No additional location-classifier extractor call.
- No additional post-reply knowledge-resolution extractor call in the same turn.

## Why
- Prevent accidental latency/cost regressions from multi-extractor pipelines.
- Keep behavior deterministic and auditable.
- Enforce one schema and one integration point for extraction mutations.

## Extractor Input (Single Call)
The single extractor receives:
- current user message,
- world locations (id -> name),
- character map (key -> name),
- previous-turn user message,
- previous-turn assistant reply,
- previous-turn unknown candidate chunks,
- bounded conversation history.

## Extractor Output Schema (JSON)
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

## Engine Application Rules
1. Apply `movement` pre-render (canonicalize to `go to <destination_id>` if valid).
2. Apply `previous_scene` into scene FIFO (`scene_knowledge_entries`).
3. Apply `knowledge_updates` into belief graph + transient mirror entries.
4. Persist current turn artifacts (`last_turn_user_msg`, `last_turn_assistant_reply`, `last_turn_retrieved_chunks`) for next turn extraction.

## Validation Rules
- `destination_id` must be in allowed world location ids; otherwise drop move.
- `previous_scene.speakers` must be allowed character keys.
- `knowledge_updates.chunk_id` must be in provided candidate list.
- Confidence values are clamped to `[0.0, 1.0]`.

## Relationship to Scene Presence
- `people_present` is computed from world graph location + character location index each turn.
- `speakers` come from extractor output for previous turn and carry into scene context when location is unchanged.

## Ownership
- Runtime implementation: `backend/app/engine/extractors/turn_extractor.py`
- Prompt-engine integration: `backend/app/api/prompt_engine.py`
- Flow trace: `documentation/model_output_docs/MESSAGE_TO_PROMPT_FLOW_TRACE.md`
