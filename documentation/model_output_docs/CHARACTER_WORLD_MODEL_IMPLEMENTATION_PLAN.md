# Character & World Model — Implementation Plan (steps 1-8)

> **What this doc is for:** The concrete implementation plan for redesign steps 1-8 of
> [CHARACTER_WORLD_MODEL_REDESIGN.md](CHARACTER_WORLD_MODEL_REDESIGN.md): modules, data structures, integration points, story
> data, tests, and rollout. Edit it when the plan changes during implementation; mark steps done with their commit.
>
> Date: 2026-09-25. Step 0 (BL-26) is done in `926bafe`.

## 0. Ground rules

- **Generic engine, story data drives the differences.** No story name appears in `world_model/` code. Everything
  story-specific lives in story JSON (optional sections; a story without them still works with defaults).
- **Pure and deterministic.** `world_model/` never calls an LLM or does I/O. Randomness comes from a seeded
  `random.Random(f"{seed}:{purpose}:{minute}")`, so replays, retries and save/resume agree. An optional `scorer`
  callable (Jev hook) can be injected for off-screen outcome scoring, and it's off by default.
- **Turn-based time.** The world advances only across the interval a player turn consumed (`minute_before → minute_after`).
  Closing the app freezes it.
- **Additive integration.** The existing prompt layers stay. The world model adds one prompt section, a header line and
  a speaker constraint, and writes into `character_locations` so current presence code keeps working. A kill switch
  `WORLD_MODEL_ENABLED` (settings, default on) plus story opt-out `world_model.enabled: false` returns to today's
  behavior exactly.
- **Preserve other agents' work:** the welcome party (`engine/opening_scene.py::stage_opening_scene`, `opening_cast`,
  `opening_scene_brief`), cast lifecycle, the whereabouts block, and the dialogue filters.

## 1. Package layout: `backend/app/engine/world_model/`

| Module | Contents | Step |
|---|---|---|
| `entities.py` | `Entity(id, kind: character/object/evidence, name, props)` | 1 |
| `world.py` | `World(start_datetime, minute, where, events)`; derived `contents`; `move()`, `where_is()`, `contents_of()`, `time_of_day()`, `weekday()` | 1 |
| `character.py` | `CharacterState(id, availability, activity, mood, aim, last_spoke_turn, initiative_score, contact)`, `get_location(world)` | 1 |
| `projection.py` | `CharacterCard` lanes + `project()` + `render_scene_section()` + `render_header()` | 1, extended by later steps |
| `model.py` | `WorldModel` aggregate: world, characters, memories, threads, contact queue, speaker plan, seed, version; `to_dict/from_dict` | 1 |
| `bootstrap.py` | `build_world_model(state)` for new games and old saves | 1 |
| `events.py` | `Event(id, minute, place, participants, truth, visibility, kind)` | 2 |
| `memory.py` | `Ref`, `Memory`, `MemoryStore` (per owner, `add`, `search(owner, query, mentions, k)`, `render(memory, viewer)`) | 2 |
| `routine.py` | `RoutineBlock`, `Routine`, `resolve(character, minute, rng)`, default sleep routine | 3 |
| `stepper.py` | `step_world(model, from_min, to_min, scene)`: chronological boundaries, anti-vanish rule, returns `Transition`s | 3 |
| `speakers.py` | `select_speakers(model, present, player_msg, turn)` → `SpeakerPlan` | 4 |
| `threads.py` | `Thread`, `Milestone`, `advance_threads(model, from, to)` | 5 |
| `commitments.py` | `add_commitment`, `due_commitments`, `resolve_commitment` (promise memories with `due`) | 5 |
| `offscreen.py` | `find_encounters`, `outcome_set`, `resolve_offscreen(model, graph, from, to, scene, scorer=None)` | 6 |
| `gossip.py` | `share_memory(model, teller, listener, minute, rng)` | 6 |
| `contact.py` | `ContactMessage`, `queue_contacts(model, from, to, scene)`, `deliver(model)` | 7 |
| `evidence.py` | `Evidence` props (`surfaces`, `requires`), `find_inspect_target`, `inspect(model, viewer, target)` | 8 |
| `turn.py` | Orchestrator: `begin_turn(state, msg, minute_before)` and `end_turn(state, msg, segments)` | 1-8 |

## 2. Step-by-step

### Step 1: character object, world location index, `move()`, `project()`
- **`World`**
  - `where: dict[entity_id, location_id]` is the single source. `contents` is derived: rebuilt from `where` on
    load and kept in sync inside `move()` (the only writer).
  - Containers: a location may be another entity ID. `contents_of(place, recursive=True)`.
  - `time_of_day(minute)` comes from `start_datetime + minute`.
- **`CharacterState`**
  - Holds availability (`awake|busy|out|asleep`), activity text, mood, aim and the recency fields.
  - `get_location(world)` returns `world.where[self.id]`.
- **Mood and relationship are per character.** `CharacterState.mood` starts from the story emotion. The per-character
  relationship to the player is read from the character graph edge (`npc → player`), not the focal-only
  `GameState.relationship`.
- **Sync with existing state.**
  - `turn.begin_turn` mirrors the player's `state.location_id` into `world.where["player"]`.
  - After `move()`s, `state.character_locations` is rewritten from `world.where`, so the existing
    `get_people_present_keys`, whereabouts block and welcome party keep working unchanged. `character_locations`
    becomes a projection of the world index.
- **Bootstrap.**
  - Runs on newgame *after* `_gather_opening_residents` and `stage_opening_scene`, seeding `where` from the staged
    `character_locations`.
  - Characters with no tracked location (IU's ghost, for example) are "unplaced": never constrained or moved.
  - Old saves build a world model lazily on first load.
- **`project(character, model, viewer, scene)`** returns lanes: `scene` (place, activity, availability, can_hear),
  `must_address`, `perspective` (memory slice), `optional`.
- **`render_scene_section`** emits `### PEOPLE AND STATE (world model)`:
  - one card per present or contactable character
  - the speaker plan
  - must-address items
  - visible off-screen traces
- **Save/restore:** a new `GameState.world_model` field, serialized under `"world_model"`, and restored.

### Step 2: per-character memory, events, per-speaker retrieval, dead-code removal
- **Events and memories**
  - `Event` records world truth and never changes.
  - `Memory` has `owner, event_id?, text` (with `@id` refs), `refs[Ref(descriptor, actual, identified)]`,
    `source` (`witnessed|told_by:<id>|overheard|authored|promised`), `confidence`, `minute`, `due`, `kind`
    (`fact|lore|promise|contact`) and `private`.
- **Rendering.** `render(memory, viewer_names)` turns `@id` into the character's name, or into a descriptor when the
  viewer hasn't learned the name. `actual` is never rendered.
- **Search.** `search(owner, query, mentions, k)` scores by token overlap (BM25-style) plus a boost for memories that
  mention an `@id` present in the player's message, with a recency tiebreak. It returns only that owner's memories.
- **Writers.**
  - On-screen, each turn:
    - The player's message becomes a `told_by:player` memory for every present, awake character.
    - Each NPC dialogue segment becomes a `witnessed` memory for every present, awake character, and the speaker
      keeps it as their own words.
  - Authored lore: the story's knowledge bundle chunks are imported as `lore` memories owned by the story's
    knowledge character (IU → `iu`), lazily with a cap. Canonical facts with `known_by` become `authored` memories
    for their owners.
- **Prompt.** Each selected speaker's card carries `perspective`: the top 3 memories from their own store.
- **Dead code removal** (only what is verifiably unreferenced):
  - the unused prompt_builder helpers (`_canonical_section`, `_canonical_facts_for_speaker`, `_format_memory_block`,
    `_places_graph_section`, `_room_relationship_section`)
  - the unimported `extractors/knowledge_resolution_extractor.py`
  - Each deletion is proven by grep plus the full suite. Stores still read by tests or playback (`epistemic_log`,
    `observation_log`) stay, recorded as a follow-up backlog item.

### Step 3: routines and the world stepper
- **Routine data.** A `Routine` is a list of `RoutineBlock(days, start, end, place, activity, availability,
  variance_min)`.
  - Default for every character: asleep 23:30-07:00 in their `home` place (a story-given or current location).
  - Story data: `routines: {templates: {...}, characters: {key: {template, home, blocks}}}`.
- **`resolve(character, minute, rng)`** returns the active block, with block edges jittered by a seeded ±variance per
  day.
- **`step_world(model, from, to, scene)`**
  - Iterates the ordered boundary minutes in `(from, to]`. At each one it moves characters (`world.move`) and sets
    availability.
  - **Anti-vanish rule:** a character present with the player at the start of the interval isn't moved out unless
    the block is `hard` (sleep after 01:00, or a hard commitment) or the interval is at least 60 minutes (time skip,
    sleep).
  - Returns `Transition(minute, character, from, to, reason)`.
  - Transitions visible to the player become "just left / just arrived" traces in the scene section.
- **Sleep.** A deterministic "I go to sleep / go to bed / sleep until morning" message is treated as sleeping until
  the next 07:00: it reuses `advance_time_by`, the player's availability is `asleep`, and the narration cue is "The
  night passes". The existing `__cmd_skip__` presets go through the same interval processing.
- **Six Strangers data:** templates (student, office, creative, service, athlete, model) and a template per character
  from their role; `home` = their bedroom by slot group.
- **IU data:** suspects' workday blocks (office, studio, café, home).

### Step 4: speaker selection and initiative
- **Candidates:** characters who are present, awake and scene-eligible. Unplaced characters count as present in
  stories without tracked locations.
- **Score:**
  - addressed by name or id in the player message: +5
  - mentioned: +2
  - edge warmth toward the player (trust + affection): +1
  - active thread or commitment topic overlap: +1
  - spoke last turn: -2
  - spoke two turns ago: -1
  - rotating initiative bonus for the longest-silent character: +1.5
- **Picking.** Pick one speaker, plus up to two more when the player addressed the group ("everyone", "you all",
  "guys") or when the scores are close (within 1.0); maximum 3.
- **`SpeakerPlan(primary, secondary, initiative, silent_present)`** goes into the scene section: "Speakers this beat:
  … Others present may react silently; do not give them dialogue unless directly addressed."
- **Enforcement.**
  - `dialogue_response_format` restricts `speaker_id` to present ∪ planned ∪ contact characters ∪ `unknown`, when a
    world model with placed characters exists.
  - After the reply, the speakers who actually spoke update `last_spoke_turn`.
- **Varied endings.** Recent ending kinds (question / offer / action / quiet) are tracked from the last dialogue
  segment. The section suggests an ending kind different from the last two.

### Step 5: threads and commitments
- **`Thread(id, owner, title, milestones, status)`** with `Milestone(id, at_day, at_time, place?, text, visibility,
  memory_for[])`.
  - `advance_threads` fires the milestones crossed in `(from, to]`, in order.
  - Each fired milestone creates an `Event` and memories for the owner and `memory_for`. A public milestone adds a
    visible trace and an `optional` card lane.
- **Commitments.**
  - `add_commitment(owner, beneficiary, text, due_minute)` creates a `promise` memory for both parties.
  - `due_commitments(minute, present)` feeds the `must_address` lane when due and the owner is present, or feeds
    contact (step 7) when they're apart.
  - Resolved or expired commitments get a status.
- **Commitment creation.**
  - A deterministic detector on NPC dialogue ("I'll … tomorrow / tonight / later / at <time>", "I promise …") creates
    NPC→player commitments.
  - Player promises in the player message ("I'll …") create player→NPC commitments for the addressed NPC.
  - It's conservative: only first-person future statements with a time phrase.
- **Story data:** `threads: [...]` per character. Six Strangers: one thread per character from its authored private
  concern (for example Momoka's audition with rehearsal, the day before, and audition-day milestones).

### Step 6: off-screen resolution, NPC↔NPC edges, gossip
- **NPC↔NPC edges.** At newgame, `process_first_meetings` runs over all active NPC pairs (already true for
  lifecycle stories), which makes sure edges exist. Off-screen outcomes update them with
  `graph.update_edge(from, to, deltas)`.
- **`find_encounters`.** It walks the stepped interval in 30-minute slices and finds pairs that are co-located and
  awake, not with the player, for at least 30 minutes.
- **`outcome_set(a, b)`.** Options: nothing, chat, shared activity, conflict, affection, plan, gossip. Each has a base
  weight adjusted by edge trust/affection/suspicion and by shared thread topics.
  - The seeded draw optionally takes a `scorer` (Jev) to reweight.
  - At most one outcome per pair per interval, and at most 6 encounters per interval (a performance and noise cap).
- **Committing an outcome:**
  - an `Event` (private to its participants)
  - memories for both participants
  - edge deltas (for example affection +0.05 for chat, suspicion +0.05 and trust -0.05 for conflict)
  - a visible trace when relevant (`conflict` → "{a} and {b} seem to be avoiding each other")
  - `plan` → a commitment between the pair
- **Gossip.** In a `gossip` outcome, or on-screen when a character speaks while another is present, one non-private
  memory the teller holds and the listener lacks is copied as `told_by:<teller>` with confidence × 0.8 and the same
  `event_id`.
- **Departure.** Off-screen outcomes never force a departure. The existing `committed_intent` path owns departures.
  Off-screen conflict only raises the departure-relevant edge values.

### Step 7: contact channel
- **Queuing.** `queue_contacts` runs on the interval when the character is apart from the player, awake, and either
  has a due commitment to the player or a thread milestone involving the player, or (rarely, seeded) has high
  affection (≥0.6) at most once per day.
  - It creates `ContactMessage(sender, minute, intent, kind: text|call)` and a `contact` memory for the sender.
- **Delivery.** `deliver` hands pending messages to the scene section's must-address lane: "Your phone buzzed while
  you were busy: {sender} texted — intent: {intent}. Mention it naturally and let the player respond."
  - Delivered messages are marked delivered. There's no UI log: the message only appears in prose.
- **Asleep senders never send.** Messages to an asleep player are delivered when the player wakes up.

### Step 8: evidence
- **Story data:** `entities: [{id, kind: evidence|object, name, location, surfaces: [{text, requires: {tool?,
  attention?}}], truth_event?, aliases}]`.
- **Inspection.** `find_inspect_target(msg, model, place)` detects an inspect intent ("examine / inspect / look at /
  search / check" + an alias match) against entities in the player's place, including container contents.
- **`inspect`.**
  - Returns the surfaces the player can perceive (their `requires` are satisfied).
  - Writes `witnessed` memories for the player (and for present NPCs, who noticed you looking).
  - Adds a `must_address` item: "The player inspects {name}: they notice {surfaces}. Describe exactly this; invent
    no other clue."
  - An evidence item's hidden `truth_event` link is never rendered.
- **IU data:** entities from the authored `leads`: `closet_scuff` (iu_apartment_room), `lyric_page` (a notebook
  page, absent from the room), `cctv_side_entrance` (local_cafe). All consistent with the existing leads text.

## 3. Integration points (exact)

| Where | Change |
|---|---|
| `engine/state.py` `GameState` | `world_model: Optional[Any] = None` |
| `api/prompt_engine.py` newgame | after `stage_opening_scene` + lifecycle + graph seeding: `state.world_model = build_world_model(state)` |
| `api/prompt_engine.py` turn | record `minute_before` before `advance_time`. After movement and time are resolved, before prompt build: `world_model.turn.begin_turn(state, msg, minute_before)` (steps time: routines → threads → off-screen → contact; writes the player-message memory; runs evidence inspection; plans speakers) |
| `api/prompt_engine.py` after reply | `end_turn(state, msg, segments)` (dialogue memories, gossip on-screen, commitments detection, speaker recency, ending kind) |
| `_serialize_state` / restore | `"world_model": state.world_model.to_dict()`; restore `WorldModel.from_dict`, or lazy bootstrap |
| `prompt_builder.system_prompt` | add `world_model_section` after `scene_brief` |
| `prompt_builder.build_messages` header | append `render_header` (speakers + must-address one-liner) |
| `dialogue.dialogue_response_format` | speaker enum narrowed by the speaker plan when available |
| sleep detection | `prompt_engine` turn: sleep phrase → `advance_time_by` to the next 07:00 + narration cue (generic) |
| settings | `WORLD_MODEL_ENABLED` (env, default true) |

## 4. Tests (per step, in `tests/backend/app/engine/world_model/`)

1. **world/character:**
   - `move` keeps `where` and `contents` consistent; containers move their contents
   - `get_location` reads the index
   - the round trip `to_dict/from_dict` is lossless, with `contents` rebuilt
   - bootstrap seeds from staged welcome-party locations; unplaced characters are never moved
   - `project` excludes unarrived characters
2. **memory:**
   - `@id` renders a name only for viewers who know it; descriptors never leak `actual`
   - `search` returns only the owner's memories and ranks mention boosts first
   - player message memories go to present awake characters only; asleep and absent characters get none
   - lore import is capped
3. **routine/stepper:**
   - seeded determinism (same seed gives the same result)
   - boundaries are crossed in order over an 8-hour sleep
   - the anti-vanish rule holds for short intervals and releases for long ones
   - sleep sets `asleep`; the default routine applies with no story data
   - `character_locations` is mirrored
4. **speakers:**
   - the addressed character is primary
   - a group address gives 2-3 speakers
   - recency rotation prevents one character dominating across 6 turns
   - absent or asleep characters are never chosen
   - the enum is narrowed only when a plan exists
5. **threads/commitments:**
   - milestones fire once, in order, across long skips
   - memories go only to the owner and `memory_for`
   - a commitment due while present puts must-address in the card; while apart it goes to contact
   - the detector ignores non-time statements
6. **off-screen:**
   - encounters only for co-located awake pairs
   - deterministic outcomes per seed
   - edge deltas applied; memories only for participants
   - gossip creates `told_by` with lower confidence and never reaches third parties
   - encounter cap respected
   - no departures forced
7. **contact:**
   - queued only when apart and awake with a reason
   - delivered once, into must-address
   - a message to an asleep player waits until they wake
   - daily cap
8. **evidence:**
   - inspecting a present alias returns only perceivable surfaces
   - `requires` gating works
   - absent evidence can't be inspected
   - a witnessed memory is created
   - `truth_event` is never rendered
9. **Integration (`/api/chat` with a fake LLM):**
   - newgame creates a world model for both stories
   - the prompt contains the world-model section with speakers
   - the save/restore round trip works
   - a sleep command advances to 07:00 and runs off-screen resolution
   - the kill switch reproduces the previous prompt byte for byte (golden comparison with the flag off)
   - all existing welcome-party, whereabouts and echo tests still pass

## 5. Verification and rollout

1. Full suite, plus deploy-gate mode (`TESTS_BLOCK_LLM_NETWORK=1`, `-m "not integration"`).
2. Local live runs with the real model:
   - Six Strangers, 3 rosters × 6 turns, including "I go to sleep" then "where is everyone?" the next morning
   - IU: inspect the closet, and a speaker check
3. Push to beta (after coordinating with the other session's gate window).
4. Hosted beta replay.
5. Prod only through `/promote-to-prod`, on user request.

## 6. Known limits (become backlog items when shipped)
- Commitment detection is heuristic (regex). An extractor-based detector is the follow-up.
- Off-screen outcomes are weighted draws, not LLM-written scenes: consequences surface through traces, memories and
  edges only.
- `epistemic_log` / `observation_log` removal is deferred until the playback tests are migrated.

## 7. As built (2026-09-25)

All steps 1-8 are implemented in `backend/app/engine/world_model/` (16 modules, entry point `turn.py`), with story data
for Six Strangers (17 routines, 17 threads) and IU (4 suspect routines, 1 thread, 2 evidence entities from the authored
`leads`). Tests: 78 new ones (`tests/backend/app/engine/world_model/`: 68 unit + authoring-guard tests;
`tests/backend/app/api/test_prompt_engine.py`: 10 `/api/chat` integration tests). The full suite passes (1147).

Differences from the plan, found during implementation:
- **Story config whitelist.** `_canonicalize_story_cfg` drops unknown story keys, so `world_model` had to be added to it.
  Without that, routines/threads/evidence silently never loaded. The integration tests now cover the real newgame path.
- **Opening placement is authoritative.** Characters adopt the routine block active at the moment they enter the world
  *without being moved* (`bootstrap.settle_into_current_block`). Otherwise a chef on an evening shift would be pulled out
  of the staged welcome-party dinner on turn 1.
- **Mood.** `Character.emotion` defaults to the story's opening emotion (the player's arrival mood), so per-character
  mood is read only from the optional `world_model.moods` map.
- **Routines are opt-in per character.** A character not listed under `world_model.routines.characters` (the IU ghost)
  gets no routine, not even default sleep.
- **Initiative tie.** Before anyone has spoken, everyone ties as "longest silent". The initiative bonus goes only to a
  *unique* longest-silent character, and thread-topic relevance weighs +2.
- **Phone calls.** On-call characters stay allowed speakers when the schema is narrowed to present people.
- **Sleep phrase** is first-person/imperative only ("Did you go to bed late?" does not trigger it).
- **Dead code removed:** `prompt_builder._canonical_section` and `_places_graph_section` (unreferenced).
  `_canonical_facts_for_speaker`, `_format_memory_block`, `_room_relationship_section` and
  `knowledge_resolution_extractor.py` are still referenced by tests or playback scenarios and stay.
- Unrelated, found while running the suite: the live-LLM `test_location_extractor_playback` is flaky (BL-30).


## 8. QC round 1 (2026-09-25): findings and plan

| Item | Finding (measured) | Plan |
|---|---|---|
| Opening re-narration (BL-29) | 0/12 local turn-1 replies; about 1 in 8 on hosted beta. The failure is a *near*-verbatim retelling of the opening paragraph, which `drop_repeated_lines` (exact match only) misses. | Treat narration as a repeat when its word-trigram overlap with a recent reply is at least 0.6 (at least 8 words), so `only_repeats` triggers the existing single regeneration. Test with the observed beta text. |
| BL-30 flaky playback test | 0/4 full-suite failures when idle; failures coincided with a concurrent arena gate. The legacy `LocationExtractor` maps a 429 to intent NONE, so `extract_expect_move` fails. It isn't used by the live turn pipeline. | Retry once on 429/5xx, honoring `Retry-After` / "try again in Xms" (capped at 2 s). Unit test: a 429 then a 200 gives MOVE. Close BL-30. |
| Storyteller 429s (seen in gates) | The public "story master unavailable" error is returned on the first 429; OpenAI's body says "try again in 322ms". | The same bounded retry on the storyteller call (one retry, at most 2 s), with a test. Timeouts stay BL-28. |
| Promise detection | Pattern-based. | Measure precision and recall on live dialogue first; move it to the extractor only if the numbers justify it. |
| Six Strangers Jev 0.00 | Last gate: 2 prod wins, 10 unresolved, on nearly identical releases. | Run the hosted arena gate beta (world model) vs prod as QC after the fixes. Read the per-game table, the length table and the world-model-specific failures. |

### QC round 1 results (2026-09-25)
- **Promises:** moved to the turn extractor (`CommitmentUpdate`, rule 11), and the regex detector was deleted. Live, 6 games:
  - regex: 12 detected, of which 6 were false positives ("I'm going to be late" recorded as a promise), and 0 NPC promises
  - extractor: 24 detected, about 23 correct (one owner flip whose wording is already from the owner's side)
  - NPC "save you dinner" caught in 6 of 6 games, and meal words set the due time (dinner -> 19:00)
  - deterministic safety nets: request owner-flip ("show me" -> the doer owns it), near-duplicate dedupe
- **Re-narration:** narration with >= 0.6 trigram overlap with a recent reply now counts as a repeat, so a turn that only
  re-tells the opening triggers the single regeneration. Local turn-1 re-narration was 0 in 12 before the change.
- **429s:** `backend/app/llm/retry.py`, one bounded retry (at most 2 s, honoring Retry-After and "try again in Xms"),
  on both storyteller calls and the legacy location extractor. Closes BL-30.
