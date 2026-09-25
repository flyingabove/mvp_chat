Logical Bug Audit — Backend Codebase
======================================

> **What this doc is for:** Catalog of logic bugs found during audits, with root causes and fixes. Edit this doc when a new logic bug is discovered and resolved.

Performed February 2026. Full read of all Python files under:
  backend/app/api/, backend/app/engine/, backend/app/config/,
  backend/app/knowledge/, scripts/scorer/story_agent_ui.py

STATUS: All 13 bugs (BUG-01 through BUG-13) have been FIXED as of February 2026.
Tests added to cover each fix. 255 tests pass.

Bugs are ordered by severity: HIGH → MEDIUM → LOW.
Each entry includes: file:line, description, impact, correct behavior, fix.

================================================================================
HIGH SEVERITY
================================================================================

BUG-01 · add_transient_entry ignores all parameters except text  [FIXED]
------------------------------------------------------------------------
File: backend/app/engine/state.py:239–255

Problem:
  The method signature accepts `id`, `namespace`, `scope`, `expires_after_turns`,
  `expires_after_minutes`, `promotable`, and `meta` but the body ignores all of them:

    self.transient_entries.append(
        TransientKnowledge(text=text.strip(), turns_remaining=TRANSIENT_KNOWLEDGE_TURNS)
    )

  Every caller that passes custom `expires_after_turns` is silently ignored. For example:

    state.add_transient_entry(..., expires_after_turns=1)   # still lasts 8 turns
    state.add_transient_entry(..., expires_after_turns=999) # also lasts 8 turns

  The `id`, `namespace`, `scope`, `promotable`, and `meta` fields are also silently dropped.
  No warning is emitted, no error is raised.

Impact:
  - Any code wanting short-lived entries (TTL < 8) will get 8-turn persistence instead.
  - Any code relying on `id` for deduplication or `scope` for cleanup will silently fail.
  - Currently harmless because all callers happen to use the same TTL as the default,
    but the API contract is broken and will mislead future callers.

Correct behavior:
  Use `expires_after_turns` (not the constant) when creating TransientKnowledge:
    turns_remaining = expires_after_turns if expires_after_turns is not None else TRANSIENT_KNOWLEDGE_TURNS
    self.transient_entries.append(TransientKnowledge(text=text.strip(), turns_remaining=turns_remaining))


BUG-02 · clear_location_transient_entries is a no-op  [FIXED]
------------------------------------------------------------------------
File: backend/app/engine/state.py:264–265

Problem:
  The method body is a bare `return` with no implementation:

    def clear_location_transient_entries(self) -> None:
        return

  This method is called in gameplay.py after successful travel to clear
  location-specific scene context when the player moves to a new location.
  Because it does nothing, all transient entries accumulated at location A
  persist when the player moves to location B.

Impact:
  - Stale scene context bleeds across location transitions.
  - A "Player said X to IU at the apartment" entry survives into a scene at
    the café, potentially influencing NPC behavior incorrectly.
  - Location-scoped transient knowledge (KnowledgeResolution from location A,
    etc.) pollutes subsequent turns in a different location.

Correct behavior:
  Filter out transient entries scoped to the previous location, or at minimum
  purge entries tagged with location-specific scope. At the simplest level:
    def clear_location_transient_entries(self) -> None:
        # Remove entries that are location-scoped (not conversation-wide)
        self.transient_entries = [
            e for e in self.transient_entries
            if not self._is_location_scoped(e)
        ]


================================================================================
MEDIUM SEVERITY
================================================================================

BUG-03 · STATE tag regex fails silently on nested JSON objects  [FIXED]
------------------------------------------------------------------------
File: backend/app/engine/state.py:328–345

Problem:
  The regex used to extract [[STATE]] tags uses non-greedy matching:

    re.search(r"\[\[STATE\]\](\{.*?\})\[\[/STATE\]\]", reply, re.S)

  `\{.*?\}` stops at the FIRST closing `}` found. For nested JSON objects,
  this captures a malformed substring that fails json.loads() and the entire
  state update is silently dropped.

  Example: model output containing
    [[STATE]]{"emotion": "wary", "extra": {"x": 1}}[[/STATE]]
  results in `m.group(1)` = `{"emotion": "wary", "extra": {"x": 1}` — invalid JSON.

Impact:
  - Any STATE tag with nested objects is silently ignored.
  - The model's intended emotion/rel_delta update is lost without any warning.
  - In current practice, STATE tags are flat objects so this is latent, but any
    future extension adding nested fields (e.g., per-character updates) will break.

Correct behavior:
  Use a balanced-brace parser or change the regex to match up to the closing
  `[[/STATE]]` delimiter regardless of brace depth:
    re.search(r"\[\[STATE\]\](.*?)\[\[/STATE\]\]", reply, re.S)
  Then let json.loads() validate the captured content.


BUG-04 · __character_location_marker__ entries written but never read  [FIXED]
------------------------------------------------------------------------
File: backend/app/api/prompt_engine.py:391–410

Problem:
  `_upsert_character_location_markers` writes entries like
  `__character_location_marker__:iu:iu_apartment_room` to the transient buffer
  every turn. Nothing in the production code reads these markers for any logic.

  - `_get_active_character_keys` (prompt_builder) reads `__active_character_marker__`, not this.
  - `get_character_location_index` reads `state.character_locations` directly, not these markers.
  - `_scene_cast_keys` also reads `location_speakers` / `character_locations` directly.

Impact:
  - Fills the transient buffer with noise each turn (one entry per character).
  - All these entries decay through the TTL system but serve no functional purpose.
  - They appear in the debug panel as transient entries, which is misleading.
  - The `add_transient_entry` overhead compounds with BUG-01 (parameters ignored).

Correct behavior:
  Either:
  a) Remove `_upsert_character_location_markers` and its call site (line 1249 in
     prompt_engine.py) — the data is already accessible via state.character_locations.
  b) Or document clearly that these are debug-only markers and have no logic effect.


BUG-05 · FAISS score filtering uses O(n²) list membership  [FIXED]
------------------------------------------------------------------------
File: backend/app/knowledge/runtime/retrieve.py:61–65

Problem:
  `faiss_filtered` is a list. The score pairing loop uses `if idx in faiss_filtered`
  which is O(n) per iteration — O(n²) total:

    faiss_filtered = _filter_by_namespace(faiss_idxs, k_faiss)  # list
    for idx, score in zip(faiss_idxs, faiss_scores):
        if idx in faiss_filtered:   # O(n) list scan
            faiss_scores_filtered.append(float(score))

  With k_faiss=8 and search_k=16, this is negligible today. But if k values
  increase or many chunks exist, this degrades quadratically.

Impact:
  Performance only; logic is correct — scores are correctly paired with their indices.

Correct behavior:
  Convert to a set before the loop:
    filtered_set = set(faiss_filtered)
    for idx, score in zip(faiss_idxs, faiss_scores):
        if idx in filtered_set:
            faiss_scores_filtered.append(float(score))


BUG-06 · manifest_mode uses location string for matching, not location_id  [FIXED]
------------------------------------------------------------------------
File: backend/app/engine/gameplay.py:23–47

Problem:
  `manifest_mode` checks if the player is "at the apartment" using string fragment
  matching on `state.location` (human-readable name like "IU's Apartment"):

    manifest_rules = cfg.get("rules", {}).get("manifestation", {}).get("apartment_location_contains", [])
    loc = getattr(state, "location", "") or ""
    inside = any(k.lower() in loc for k in manifest_rules)

  The canonical location tracking now uses `state.location_id` (e.g., "iu_apartment_room").
  `state.location` is a display name that may not always match the manifest rule keywords.

Impact:
  - If `state.location` display name changes (e.g., "IU's Apartment" vs "Apartment"),
    the manifestation check silently breaks without errors.
  - The string matching is fragile: "apartment" in "IU's Apartment" works, but if
    the location name is ever changed or localized, the ghost NPC could fail to manifest.

Correct behavior:
  Use `state.location_id` with location-id-based rules instead of substring matching
  on display names. Or validate at story load that manifest_rules strings match known
  location IDs.


BUG-07 · Belief claims hard-capped at 10 without any warning  [FIXED]
------------------------------------------------------------------------
File: backend/app/engine/prompt_builder.py (belief injection section)

Problem:
  When injecting belief context into the prompt, claims are sliced to 10:

    for claim in (getattr(bs, "claims", []) or [])[:10]:

  There is no warning, no log, and no documentation of this limit. Characters
  with >10 active belief claims will silently have later claims excluded from
  the prompt context.

Impact:
  - In a long game with many resolved knowledge chunks, belief claims accumulate.
    Claims beyond the 10th are never seen by the LLM.
  - Debugging belief-based NPC behavior becomes confusing because some beliefs
    appear active in state but have no effect on prompt output.

Correct behavior:
  Either raise the cap (or make it configurable), or log when truncation occurs:
    claims_list = (getattr(bs, "claims", []) or [])
    if len(claims_list) > 10:
        _log({"kind": "belief_truncated", "character": state.main_character_id, "count": len(claims_list)})
    for claim in claims_list[:10]:


BUG-08 · Silent exception in epistemic seeding drops canonical facts without notice  [FIXED]
------------------------------------------------------------------------
File: backend/app/api/prompt_engine.py (inside _seed_epistemic_from_story)

Problem:
  Epistemic seeding uses `except Exception: continue` patterns around individual
  fact/belief parsing. If a canonical fact in the story JSON has an unexpected
  structure (e.g., wrong field types, missing required keys), it is silently
  skipped. The game starts but that fact is simply not in the knowledge stack.

Impact:
  - Story JSON authoring errors (malformed facts) are invisible at game start.
  - The NPC behaves as if the fact doesn't exist, which is confusing to debug.
  - No way to detect this without tracing through a full game session.

Correct behavior:
  Log a warning when a fact fails to parse, including the fact id and the error:
    except Exception as exc:
        _log({"kind": "fact_parse_error", "fact_index": i, "error": str(exc)})
        continue


================================================================================
LOW SEVERITY
================================================================================

BUG-09 · _certainty_word silently returns "mixed" for unexpected float values  [NOT A BUG]
------------------------------------------------------------------------
File: backend/app/engine/prompt_builder.py (_certainty_word function)

Problem:
  Confidence values are bucketed by rounding to 1 decimal place and looking up
  in a dict. If a confidence value is outside [0.0, 1.0] or doesn't round to
  an expected bucket, the dict lookup returns "mixed" via `.get(bucket, "mixed")`.

  For example, confidence=1.05 rounds to 1.0 (OK), but confidence=0.45 rounds
  to 0.4 which may or may not be in the dict depending on the defined buckets.

Impact:
  Minor — the LLM prompt gets "mixed" certainty language for unexpected confidence
  values instead of the intended phrasing. No crash, no visible error.

Correct behavior:
  Clamp confidence to [0.0, 1.0] before bucketing, and ensure all 0.1-step
  values between 0.0 and 1.0 are present in the dict.


BUG-10 · GameState.character_locations can contain empty-string location values  [FIXED]
------------------------------------------------------------------------
File: backend/app/api/prompt_engine.py (character_locations seeding)

Problem:
  At game start, character_start_locations from world config is populated as:

    new_state.character_locations = {
        str(k).strip(): str(v).strip()
        for k, v in char_start_locs.items()
        if k and v
    }

  The `if k and v` guard correctly filters out empty strings. However, later in
  the game if character_locations is updated manually with an empty location_id
  (e.g., `state.character_locations["iu"] = ""`), `get_character_location_index`
  returns a dict with `"iu": ""`. This empty-string location would cause a character
  to appear "at location ''" which matches nothing but pollutes the index.

Impact:
  Low risk in current code since character_locations are only set at game start.
  Risk increases if/when character movement APIs are added.

Correct behavior:
  Filter empty-value entries in `get_character_location_index` before returning:
    return {k: v for k, v in runtime_locs.items() if k and v}


BUG-11 · advance_time advances world_clock even if world clock doesn't track dialog time  [FIXED - doc comment added]
------------------------------------------------------------------------
File: backend/app/engine/gameplay.py:67–71

Problem:
  When a world runtime exists, dialog time is unconditionally added to world_clock:

    if runtime is not None:
        try:
            runtime.world_clock.advance(int(delta))
        except Exception:
            pass

  Then, if travel succeeds (line 108):
    state.minute = runtime.world_clock.minute

  The world clock now includes the dialog delta already advanced at line 69
  PLUS the travel time added by the travel resolver (inside resolve()). This is
  likely correct. However, the travel resolver's advance of the world clock is
  not visible here — there's implicit ordering coupling: world_clock is advanced
  twice (once for dialog, once for travel inside resolver) without this being clear.

  If the travel resolver is refactored to NOT advance the world clock internally,
  travel time would be silently lost.

Impact:
  No current bug, but fragile ordering dependency. The `resolve()` call's side
  effect of advancing world_clock is not documented at the call site.

Correct behavior:
  Document the ordering explicitly. Consider having `advance_time` advance
  world_clock by dialog time and by travel time explicitly, rather than relying
  on resolver side effects.


BUG-12 · _relationship_role_prose: character role "npc" falls through to generic message  [FIXED]
------------------------------------------------------------------------
File: backend/app/engine/prompt_builder.py (_relationship_role_prose)

Problem:
  The function has specific prose for: employer, employee, family, friend, enemy,
  lover, suspect, witness. The most common role in the codebase is "npc" (used as
  the default fallback in Character). "npc" falls through to the generic
  `f"The relationship type is npc."` which is unhelpful and slightly awkward in
  the rendered prompt.

Impact:
  LLM sees "The relationship type is npc" in the relationship context section,
  which adds no useful information and may be confusing.

Correct behavior:
  Add a case for common fallback roles like "npc" or "character":
    if token in ("npc", "character", "other", ""):
        return "This is a general relationship with no specific role defined."


BUG-13 · Story loader silently mutates first character's is_main flag  [FIXED]
------------------------------------------------------------------------
File: backend/app/engine/story_loader.py (character finalization)

Problem:
  If no character in the story JSON has `is_main: true`, the loader silently
  sets `characters[0].is_main = True` as a fallback:

    if characters and not any(c.is_main for c in characters):
        characters[0].is_main = True

  This mutation happens on the loaded Character object, which the caller
  may not expect to be modified. The game may also start with the wrong focal
  character (whoever was listed first in the JSON).

Impact:
  - Story authoring error (forgot to set is_main) produces a silently "wrong" game
    rather than a clear validation error.
  - First character in list becomes main by accident.

Correct behavior:
  Raise a validation error or at minimum emit a warning:
    _log({"kind": "story_warning", "msg": "No is_main character found; defaulting to first character"})


================================================================================
NOTES / NOT BUGS BUT WORTH KNOWING
================================================================================

N1 · knowledge_resolution_updates is always initialized before the try block
  Bug #9 from the initial audit (UnboundLocalError risk) is INCORRECT.
  `knowledge_resolution_updates: list[dict] = []` is initialized at line 1478,
  before the try block. There is no UnboundLocalError risk.

N2 · gameplay.py time advancement is correct
  When travel succeeds, state.minute is set from world_clock.minute (which includes
  both dialog time and travel time). When travel fails, state.minute is advanced by
  dialog time only (travel time not added — correct since travel didn't happen).
  Both world_clock and state.minute stay in sync through all code paths.

N3 · TransientKnowledge.turns_remaining = TRANSIENT_KNOWLEDGE_TURNS default is correct
  For markers (__active_character_marker__, __character_location_marker__), the TTL
  is irrelevant because they are removed and re-created every turn before pruning.
  The 8-turn TTL on regular content entries (KnowledgeResolution, Player said, etc.)
  is the intended design.

N4 · FAISS score filtering (BUG-05) logic is CORRECT despite O(n²)
  Scores are correctly paired with their indices. The explore-agent claim about
  "index misalignment" was incorrect. It is a performance issue only.

================================================================================
SUMMARY TABLE
================================================================================

| ID    | File                          | Severity | Type                    |
|-------|-------------------------------|----------|-------------------------|
| BUG-01| state.py:239                  | HIGH     | Parameters ignored       |
| BUG-02| state.py:264                  | HIGH     | No-op method             |
| BUG-03| state.py:328                  | MEDIUM   | Regex nested JSON        |
| BUG-04| prompt_engine.py:391          | MEDIUM   | Dead code / buffer noise |
| BUG-05| retrieve.py:63                | MEDIUM   | O(n²) list membership    |
| BUG-06| gameplay.py:40                | MEDIUM   | String vs ID mismatch    |
| BUG-07| prompt_builder.py (beliefs)   | LOW      | Silent truncation        |
| BUG-08| prompt_engine.py (seeding)    | LOW      | Silent exception         |
| BUG-09| prompt_builder.py (certainty) | LOW      | Unexpected float fallback|
| BUG-10| prompt_engine.py (locations)  | LOW      | Empty value not filtered |
| BUG-11| gameplay.py:67                | LOW      | Implicit ordering        |
| BUG-12| prompt_builder.py (rel prose) | LOW      | Unhelpful "npc" output   |
| BUG-13| story_loader.py               | LOW      | Silent is_main mutation  |

## 2026-09-18 — Movement dropped dialogue and rendered the previous room's cast

Live Six Strangers verification reproduced two related defects: a request to
return to the living room and ask Makoto and Minori about their work became
only `go to living_room` in the saved transcript, and the reply confused the
baseball player with Uchi.

The turn handler overwrote `msg` with the movement command before prompt
assembly and persistence. Travel also cleared scene markers populated before
movement, allowing prompt construction to fall back to the previous scene's
occupants. Fix: use a separate movement input for `advance_time`, retain player
text throughout the conversation pipeline, and refresh destination scene
presence before rendering. Regression coverage checks both extractor and
heuristic movement, original text in the prompt/transcript, and destination
identity blocks including empty-room transitions.

## 2026-09-24 — NPC echoed the player's line; housemates' whereabouts were invented

Live prod (Six Strangers): the player typed "cool where are all the other guys
at? i want to say hi" and Makoto said it back word for word. A housemate then
answered with "Yuto should be back from practice soon", although Yuto had not
moved in.

1. `drop_player_echo` only stripped echoed sentences of at least 3 words and
   stopped at the first sentence that failed that test, so the one-word
   "Cool!" hid the echo behind it. Fix: strip the longest leading run of
   sentences that appears verbatim in the player's message once the run
   reaches 3 words, and drop a whole segment that is a lightly reworded copy
   (at least 80% of words matched in order in both directions).
2. Turn 1 put the player at `front_entry` and the NPCs in `living_room`, so
   the scene brief said "People present: none" and nothing told the model
   where anyone was. Fix: gather the opening cast and the player in the
   kitchen, and add the authoritative whereabouts block and per-turn header
   described in CAST_LIFECYCLE_DESIGN §6.
3. The `Cast IDs` list, the speaker enum and authored self-knowledge named
   unarrived residents. Fix: filter all three by scene eligibility. A prompt
   audit over 40 random rosters went from 56 unarrived-name mentions to 0.

Remaining gap: NPC positions are never updated from narration, so whereabouts
stay where the game started until arrivals or departures change them (BACKLOG
BL-24).


## 2026-09-24 (follow-up) — Storyteller re-sent the opening's lines every turn

The post-release check on prod found each turn repeating the opening greeting
("You found it. Come in; we're just setting the table."). Each copy re-entered
the history the model reads, so the repeats snowballed. One whole turn-1 reply
was nothing but the opening. Fix (`dialogue.py`): `drop_repeated_lines`
removes dialogue of at least 4 words and narration of at least 8 words that
appeared verbatim in the last 3 replies. When `only_repeats` shows a draft has
no new beat, `prompt_engine.py` regenerates once with a short correction and
logs `storyteller_repeat_regenerated`. The echo filter also strips a long
leading sentence that is at least 85% the player's words in order ("…after a
long day too."). Note: a decoded reply still carries its `[[STATE]]` tag, so
run `extract_state_tag` before judging a draft's segments, or the tag counts as
a non-repeat narration beat.
