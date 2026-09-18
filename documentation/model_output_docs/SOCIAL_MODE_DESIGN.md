# Social Mode Design — Ensemble Slice-of-Life Games

> **What this doc is for:** Describes the optional `mode` object in story JSON, how it's wired into the prompt engine, and how to author a Terrace-House-style ensemble/slice-of-life game using the existing engine primitives. Edit this doc when the `mode` schema changes or a new mode `type` is added.

## 1. Why this exists

The engine's four primitives (State, Time, Incentives, Constraints — see `GAME_DESIGN_SYSTEMS.md`) were built and battle-tested against murder-mystery stories: one central NPC (`is_main: true`), a handful of suspects, a truth to uncover. Nothing about those primitives is mystery-specific, but nothing previously told the storyteller model *not* to treat every game like a mystery either — the base prompt talks about "the investigation," "corrections," "canon," etc. in ways that read fine for a murder mystery and slightly oddly for a slice-of-life house sim.

The `mode` object is a small, purely additive prompt layer that gives the storyteller model the right tone and conventions for non-mystery ensemble games, without touching anything else. If a story doesn't declare `mode`, nothing changes — this is the backward-compatibility guarantee, and it's enforced by a test (`test_mode_context_section_byte_identical_prompt_for_existing_story` in `tests/backend/app/engine/test_prompt_builder.py`).

## 2. The `mode` schema

Optional top-level key in story JSON:

```json
"mode": {
  "type": "social_sim",
  "setting": "shared_house",
  "open_ended": true,
  "cast_size": 3,
  "confessional": {
    "enabled": true,
    "convention": "The player may address an unseen listener directly as a private aside (e.g. prefixed like a diary entry, or wrapped in [confessional: ...]); other characters never hear or react to these asides."
  },
  "daily_rhythm": [
    "Mornings are rushed — someone's always looking for their keys.",
    "Evenings are the real social currency of the house.",
    "Weekends drift."
  ]
}
```

Field-by-field:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `type` | string | yes (to activate the layer) | Names the mode. Currently one value is given special phrasing: `"social_sim"`. Any other non-empty string still activates a generic fallback sentence (`This story runs in '<type>' mode (<setting>).`) so the schema is forward-compatible with modes not yet designed. |
| `setting` | string | no | Free-text setting label, e.g. `"shared_house"`. Rendered in prose with underscores turned to spaces. |
| `open_ended` | bool | no | When true, the layer tells the storyteller there's no fixed win condition and to focus on daily life/relationships instead of a goal. This is prose-only — it does not by itself omit `goal`/`win_detection`; you still omit those keys yourself (see §4). |
| `cast_size` | int | no | Recurring-cast size, surfaced in prose ("The cast includes N recurring housemates..."). Purely descriptive. |
| `confessional.enabled` | bool | no | Turns on the confessional-convention paragraph. |
| `confessional.convention` | string | no | Custom convention text. If omitted while `enabled: true`, a sensible default sentence is used. |
| `daily_rhythm` | string[] | no | Up to a few flavor lines describing typical daily texture (used for prompt tone only, not simulated). |

Implementation: `backend/app/engine/prompt_builder.py::_mode_context_section(state)`. It reads `state.story_cfg["mode"]` and returns `""` when the key is absent/empty/malformed — so a story with no `mode` key, an empty `{}` `mode`, or a `mode` missing `type` all fall back to zero-length output.

Wiring: `backend/app/api/prompt_engine.py::_canonicalize_story_cfg` copies the raw JSON `mode` object into `story_cfg["mode"]` (it was previously not in the whitelist of keys copied into `story_cfg`, so this had to be added explicitly), and `_seed_noncanonical_story_details_to_transient` excludes `mode` from the generic "dump unknown top-level keys into transient/FAISS-ish story details" path so it isn't double-injected in raw JSON form alongside the dedicated prose layer.

## 3. Prompt layer order

The mode layer sits in `system_prompt()` immediately after `base_prompt` (the storyteller contract / narrator-voice rules) and before the scene brief:

1. Base prompt (narrator contract, style, canon-correction rules)
2. **`mode_context` (NEW — this layer)**
3. Scene brief (`SCENE BRIEF` — cast present, time, location)
4. Knowledge stack (retrieved FAISS/BM25 chunks + labeled epistemic stack)
5. Relationship context (character graph prose)
6. Character self-knowledge (identity facts — see §5 for the ensemble caveat)
7. Truth override (debug mode only)

This mirrors the position described in `documentation/model_output_docs/LAYER_COVERAGE_MAPPING.md` / the MEMORY "System Prompt Layers" list — logically it belongs right next to the base prompt/style layer, since it's tone-setting context the model should internalize before anything else, and its position is now also reflected there and in `MESSAGE_TO_PROMPT_FLOW_TRACE.md`.

`build_messages()`'s `return_debug=True` path also exposes it as `prompt_layers["mode_context"]` for the debug UI, alongside the existing `base_prompt`, `character_identity`, etc. keys.

## 4. Mapping engine primitives onto ensemble/slice-of-life play

No new mechanics were built. Everything below reuses primitives that already exist for the mystery genre:

| Primitive | Mystery usage | Ensemble/slice-of-life usage |
|---|---|---|
| `world` locations | Crime-scene rooms, offices | House rooms (kitchen, living room, bedrooms, a quiet balcony) |
| `character_self_knowledge` | The one central NPC's identity facts | The one `is_main` housemate's identity facts (see §5 — this is still single-character) |
| `epistemic_seed.canonical_facts` | Case facts, alibis | House lore/history everyone knows (`known_by: ["all_characters"]`), plus each housemate's private secret (`known_by: [<that character's key>]`) that the player can discover through conversation |
| `epistemic_seed.belief_seeds` | Suspects' self-serving beliefs | Housemates' private, sometimes self-deceiving beliefs about themselves or the house |
| `relationships.edges` | Suspect↔victim/detective trust-fear-affection-suspicion | Housemate↔player bonds **and** housemate↔housemate bonds (NPC-NPC edges), so the graph is genuinely ensemble, not hub-and-spoke |
| `opening.text` | The crime discovery scene | Move-in day — first impressions of the house and every housemate |
| `goal`/`win_detection` | A confession regex | **Omitted entirely** for an open-ended game — confirmed by `gameplay.py::win_condition_detected()` returning `False` whenever `win_detection.regex` is absent |
| `motive` (character field) | Why a suspect might have done it | Repurposed as a personal-life-goal/insecurity summary for authoring flavor (surfaced via the same transient story-detail path suspects already use — it isn't read by any dedicated prompt layer for either genre) |

## 5. Known limitation: `character_self_knowledge` is single-character

This is the one place the ensemble framing runs into a real, pre-existing engine constraint, and it's worth being explicit about rather than pretending it doesn't exist (the same policy `GAME_DESIGN_SYSTEMS.md` already applies to the missing quest/schedule engine).

`_character_identity_section()` in `prompt_builder.py` only ever reads `state.main_character.self_knowledge` — i.e. whichever character has `is_main: true` (or, per the existing BUG-13 fallback in `story_loader.py`, the first character in `characters[]` when none is explicitly flagged, logged as a `story_warning`). This is true for every existing story: in the murder mysteries, only the central ghost/victim NPC has `character_self_knowledge` entries; the suspects don't get this layer at all.

The Common Room follows the same pattern rather than extending the engine: all three housemates are authored with `is_main: false` (matching the "ensemble, no single protagonist NPC" framing), and the loader's existing fallback assigns `is_main` to the first character listed (Mina) with a logged warning — a supported, tested code path (`test_story_loader_warns_when_no_is_main_flag`), not a hack. Mina's `character_self_knowledge` block is what gets injected as the `### CHARACTER IDENTITY` section. Dae-ho and Priya's inner lives are instead carried by:
- their `motive` field (authoring flavor, same mechanism suspects use),
- their private secret as an `epistemic_seed.canonical_facts` entry scoped to just them (`known_by: ["daeho"]` etc.), discoverable through play,
- their `belief_seeds`,
- and their relationship edges (including the two NPC-NPC edges).

A future engine change to give every present character their own self-knowledge section (not just `main_character`) is tracked in `documentation/BACKLOG.md` rather than built here, since it would touch a layer shared by all 5 existing stories and was out of scope for the `mode` layer itself.

## 6. Confessional convention: prompt convention, not a bracket command

Per `documentation/ai_learnings_mistakes/AI_CREATE_NEW_FLAG.md`, a "bracket command" (`[D]`, `[M]`, `[C]`, ...) is a mechanical toggle/one-shot action intercepted in `prompt_engine.py` *before* any LLM call, and it requires matching frontend wiring (`COMMAND_PATTERNS` in `frontend/index.html`) so the client recognizes it and skips normal message handling.

The confessional aside doesn't need any of that. The player is still writing a normal in-character message; they're just narratively framing part of it as an aside to an unseen listener (a documentary-crew fourth wall, a diary entry, whatever framing the convention text describes). This is exactly the kind of "instruction to the storyteller model about how to *interpret* ordinary text" that a prompt layer is for — no parsing, no frontend change, no new state. **Decision: confessional is implemented purely as a prompt convention** (the `mode.confessional` block in §2), not a bracket command. This was chosen because:
- it requires zero frontend changes (simpler, less surface area to maintain);
- it composes for free with the existing OOC `(...)`/`[...]` convention (OOC breaks the fourth wall entirely and talks to "the author"; confessional stays in-scene and talks to an unseen in-universe listener — different registers, both handled by prompt instructions rather than parsing);
- a mechanical bracket-command version would need a real command grammar (start/end markers, escaping) to know where the confessional aside begins and ends inside a longer message, which is unnecessary complexity for what is fundamentally a tone instruction to the model, not a state change.

## 7. How to author your own `social_sim` game

Using `backend/app/stories/6_common_room/` (**The Common Room**) as the reference:

1. **Folder & files**: `backend/app/stories/<n>_<slug>/<slug>_story.json` + `<slug>_world.json`. Use the next available numeric prefix (check the highest existing one) or a descriptive folder name. The declared `id` field (not the filename) is what the content registry (`story_loader.py::build_story_registry()`) keys on — see `AI_GAME_STRUCTURE.md`.
2. **World**: model your rooms as locations with short travel edges (1-3 minutes within a house). Tag at least one location `"private"`/`"quiet"` for confessional-style private conversations (see `rooftop_balcony` in Common Room's world JSON).
3. **Cast**: 2-4 recurring characters, each with a `role`, a `motive` (repurposed as a personal-life-goal/insecurity summary, not a crime motive), and no `is_suspect`/`tells` (those are mystery-genre vocabulary and are optional fields — `Character.from_dict` in `backend/app/engine/state.py` doesn't require them). List the character you want to carry `character_self_knowledge` first if you don't want to set `is_main` explicitly (see §5).
4. **`character_self_knowledge`**: 2-4 first-person "You are..." identity facts for that one focal character, same style as the mystery stories.
5. **`epistemic_seed.canonical_facts`**: house lore everyone knows (`known_by: ["all_characters"]`) plus one private-secret fact per character (`known_by: [<key>]`) for things the player should discover through conversation, not be told upfront.
6. **`relationships.edges`**: seed every housemate→player edge, and at least one NPC-NPC edge, so `ROOM DYNAMICS` prose reflects real ensemble relationships when multiple characters share a scene.
7. **`opening.text`**: write real, evocative move-in-day (or equivalent) prose — this is a creative deliverable, not boilerplate.
8. **No `goal`/`win_detection`** if the game is meant to be open-ended — just omit both keys.
9. **`mode`**: add the block from §2 with `type: "social_sim"`.
10. **Test**: the parametrized `test_every_catalogued_story_initializes_end_to_end` in `tests/backend/app/api/test_prompt_engine.py` automatically picks up any story returned by `all_stories()`/the registry — no per-story test needed, but do add a targeted `win_condition_detected` test if you're omitting `goal`/`win_detection` (see `test_win_condition_detected_false_for_common_room_open_ended_story` in `tests/backend/app/engine/test_gameplay.py`).

## 8. Explicit limitations (read before assuming more exists)

- **No quest/schedule/resource engine.** Chore wheels, jobs, daily routines, etc. are narrative content NPCs can reference in conversation — they are not mechanically simulated (no calendar, no NPC schedules, no resource meters). See `GAME_DESIGN_SYSTEMS.md` and `documentation/BACKLOG.md`.
- **Relationship drift is asymmetric.** Only player→NPC relationship edges are updated by structured turn extraction today; NPC→player and NPC↔NPC edges are seeded at game start but not mechanically driven during play (only the main NPC has a narrative-tag-driven affection path). Tracked in `documentation/BACKLOG.md`.
- **`character_self_knowledge` is single-character** (§5) — an ensemble cast's other members rely on `motive` + per-character canonical facts/belief seeds, not their own identity-section layer.
