# World model: character world model, implementation plan, living world, atlas

> This file merges several design documents (each keeps its own section, with its original status notes). Open work is in [../backlog/](../backlog/).

## Character & World Model Redesign

> **Target-design authority, 2026-09-28:** [consolidated BL-39](SOCIAL_ENGINE.md) governs future Character/relationship ownership and hybrid decisions. This document remains a reference for existing work. Characters remain free of provider I/O while consuming application-supplied LLM/Jev proposals.

> **What this doc is for:** The agreed design for a robust character object, a world-owned location index,
> events, memories and relationship edges. Together these make the game world consistent and engaging.
> Edit this doc when the data model, a mechanic, or the build order changes.
>
> Date: 2026-09-24. Status: **implemented 2026-09-25** (steps 0-8; see [design/WORLD_MODEL.md (implementation plan)](WORLD_MODEL.md) §7 for as-built notes). Extends
> [design/WORLD_MODEL.md (living world)](WORLD_MODEL.md)
> (routines, turn packet, evidence, and the §12 owner decisions) and
> [design/SOCIAL_ENGINE.md (cast lifecycle)](SOCIAL_ENGINE.md).

---

### 1. Problems we are solving

| # | Problem | What the player sees today | Root cause in code | Fixed in step |
|---|---|---|---|---|
| P1 | **Who speaks is decided by the model** | Roll calls where 4-5 housemates talk every turn; one NPC dominates (BL-22) | No speaker-selection policy; the storyteller picks speakers freely | 4 |
| P2 | **NPCs have no personal arcs** | Nobody's life moves forward: no audition, job decision or cover story under strain (e.g. Momoka's audition) | No personal-thread or milestone model | 5 |
| P3 | **NPCs never reach out** | Nobody texts or calls when apart | No contact channel as a behavior | 7 |
| P4 | **No NPC-to-NPC relationships** | Housemates have no history with each other; gossip is impossible | `character_graph` edges exist mostly player↔NPC (BL-11); NPC↔NPC state is never updated | 6 |
| P5 | **Build order was investigation-first** | Terrace needs living routines and conversation first | Living-world §10 starts with evidence | (order below) |
| P6 | **Authored lore never reaches the prompt** (BL-26, step 0 fixed in `926bafe`) | IU answers about her life from general model knowledge, not authored facts | `retrieve_knowledge` `_filter_by_namespace` drops every authored chunk (live path: 0 of 57 IU chunks; 8 without the filter) | 0, then 2 |
| P7 | **NPCs never move and are always available** (BL-24) | Whereabouts drift from the story; nobody leaves for work, sleeps or is busy | `character_locations` only changes on opening, arrival and departure; no awake/busy/out/asleep state | 1 (availability), 3 |
| P8 | **Only the focal character has an inner life** | In group scenes, four of five speakers have no memory, mood or beliefs of their own | Mood/relationship live on `GameState` (focal only); retrieval, beliefs and knowledge filters key off `main_character_id` | 1, 2 |
| P9 | **Character state is scattered** | Bugs where one prompt layer forgets a filter (whereabouts missing, unarrived names leaking) | One character's data spans ~10 `GameState` fields; the prompt builder stitches and filters each separately | 1 |
| P10 | **Memories have no owner or source** | NPCs "know" things they never heard; a player's claim is treated as fact | `SessionChunkStore` chunks have no speaker, no audience, no provenance | 2 |
| P11 | **Short, lossy conversation memory** | Anything older than about 3 exchanges is only loose sentences | Log trimmed to 6 rendered messages; no event records | 2 |
| P12 | **No difference between truth and perspective** | No foundation for alibis, mistaken witnesses or lies | Canonical facts and beliefs are flat text; nothing records what actually happened vs. who perceived it | 2, 8 |
| P13 | **Dead and duplicate memory stores** | Harder to reason about; wasted code paths | `epistemic_log`, `observation_log`, `tells`, edge `narrative`/`disposition`, `extracted_chunks` table written but never read | 2 |
| P14 | **Objects and evidence have no place in the world** | Nothing to notice in a room; the mystery can't use physical clues | No entity/location model for objects | 1, 8 |
| P15 | **Promises are forgotten or invented** | An NPC who promised to save dinner forgets; or a favor "remembered" that was never promised | No commitment model; promises are just past dialogue that falls out of the ~3-exchange window | 5 |
| P16 | **The world freezes when the player isn't watching** | Sleep or a time skip changes nothing; housemates never date, argue or make plans off-screen | No off-screen resolution; the clock advances but no NPC activity is simulated for the elapsed game time | 6 |

### 2. Owner decisions (constraints on every mechanic)

1. **Turn-based clock.** Game time advances only when the player takes a turn. Closing the app freezes the world. One turn
   can cover hours (sleep = 8 hours), and awake NPCs may produce that many hours of change in one resolution step.
2. **Full off-screen autonomy.** While the player sleeps or is away, NPCs may date, fight, make plans or decide to leave.
3. **No log UI, ever.** No house log or event feed. The player learns only through the story: being told, noticing
   consequences, overhearing.
4. **Generic first.** Every mechanism is engine code plus story data and works in every story. Routines serve both
   housemate schedules and suspect alibis.
5. **The engine owns facts, the storyteller writes the scene.** The LLM never decides where people are, what happened
   or who knows what. Characters never call an LLM; they are data plus deterministic, seeded methods.

### 3. Data model

Four collections of plain data are saved with the game. Everything else is a query over them.

```
world         clock, where{entity_id -> place_id}, events[]       (contents{} is derived)
characters    identity, availability/activity, routine, mind, commitments, threads, contact
relationships from, to, trust/affection/fear/suspicion, label, impressions    (feelings only)
memories      owner, event?, text-with-@ids, refs[], source, confidence, time, due?
```

Objects and evidence are **entities** like characters: an ID, properties, and whatever can be noticed about them.

#### 3.1 Location: the world owns it

```
world.where[entity_id]   -> place_id           # uchi -> kitchen, covered_plate -> kitchen
world.contents[place_id] -> {entity_ids}       # kitchen -> {uchi, arisa, covered_plate}
```

- One index covers everything that can be somewhere: characters, objects, evidence. `world.contents[B]` answers
  "who and what is in B?" in one lookup, filtered by entity type when needed.
- `character.get_location()` is `return world.where[self.id]`. The character never stores its own location, so there is
  no second copy to drift.
- **Single writer:** `world.move(entity_id, to)` is the only function that changes location and updates both maps
  together. Player travel, routines, picking up an object and an NPC leaving mid-scene all use it.
- Only `where` is saved; `contents` is rebuilt on load, so a save can never contain an index that disagrees with itself.
  (`GameState.character_locations` is the existing id→place map this grows from.)
- Containers: an entity's location may be another entity (`letter -> desk_drawer -> study`). Moving the container
  moves its contents. This is optional and can come later.

#### 3.2 Character

| Part | Holds |
|---|---|
| Identity | id, name, role, voice, self-knowledge, authored personality |
| Body | availability (`awake` / `busy` / `out` / `asleep`), current activity; location via `get_location()` |
| Routine | activity blocks by weekday and time, seeded variance, exceptions (appointments, promises) |
| Mind | mood, current scene aim, initiative budget |
| Commitments | promises made to or by them, each with a due time |
| Threads | 2-3 personal storylines with time-based milestones |
| Contact | whether and when they would text or call the player |
| Lifecycle | upcoming / active / departed (from `cast_lifecycle`) |
| Memory | their memories (§3.5); retrieval searches only these |

Mood and relationship move from focal-only `GameState` fields onto every character (P8).

#### 3.3 Relationship edges: feelings only

A directed edge `from → to` records how one character feels about another *now*: trust, affection, fear, suspicion,
a static label, and short impressions. This includes NPC↔NPC edges (P4). Edges are **not** a record of what happened;
that lives in events and memories. "Do A and B share a past?" is a query (events where both took part), not a stored
edge.

#### 3.4 Events: what actually happened (world truth)

```json
{ "id": "E17", "time": "2021-06-03T19:00", "place": "yoyogi_park",
  "participants": ["a", "b"], "truth": "@a and @b argued about the money", "visibility": "private" }
```

Events come from authored backstory (for example the night of a crime), off-screen resolution, and accepted on-screen
outcomes. Once committed, an event never changes. Lies and mistakes live in memories, not events.

#### 3.5 Memories: one character's perspective

```json
{ "owner": "a", "event": "E17", "text": "I argued with @b about the money", "source": "witnessed", "confidence": 1.0 }

{ "owner": "c", "event": "E17", "text": "two people arguing near the fountain; one wore a blue jacket",
  "refs": [{ "descriptor": "person in a blue jacket", "actual": "b", "identified": false }],
  "source": "witnessed", "confidence": 0.7 }

{ "owner": "d", "event": "E17", "text": "@a says @a and @b fought over money", "source": "told_by:a", "confidence": 0.6 }
```

- **`@id` means the owner knew who it was.** It is rendered as a name only for a viewer who knows that name ("Uchi"),
  otherwise as a description ("the hair stylist"), which also tracks whether the player has learned a name.
- **Unsure identification stays a descriptor.** `actual` is **engine-only**: it is never sent to the LLM and never shown
  to the player. It lets the engine offer a later recognition moment (C sees B in the blue jacket). This is the
  witness and alibi model for mysteries: the truth is in events, and each person holds a partial view.
- **Every memory enters through a channel:** `witnessed`, `told_by:<id>`, `overheard`, `authored`. Gossip is a
  `told_by` memory pointing at the same event with lower confidence, so rumor chains are traceable.
- **Promises** are memories with `due`. **Authored lore** becomes `authored` memories owned by the character; this
  replaces the story-wide FAISS/BM25 bundle and fixes P6 permanently.
- A player's statement becomes a `told_by:player` memory for each character who heard it. It is never a fact (P10).

#### 3.6 Objects and evidence

An entity with an ID, a location from `world.where`, authored properties, and "noticeable" surfaces that depend on
light, access, tool and time. A character's knowledge *of* evidence is a memory ("I saw the scratch at 22:00"); the
evidence itself exists whether or not anyone knows it. Full evidence ecology: living-world doc §3.

### 4. Mechanics

#### 4.1 Moving and arriving (A → B)
1. `world.move(player, B)` advances the clock by the route time; the routine stepper updates everyone for those minutes.
2. `world.contents[B]` gives the characters and objects there.
3. Each awake character reacts to the player according to their edge and meeting history (a warm greeting, a cold nod, ignoring them).
4. Speaker selection (§4.3) picks who talks; objects become things to notice or inspect.

#### 4.2 Context projection: the only way character data reaches the LLM
`character.project(scene, viewer, budget)` returns lanes (living-world §6):
- **Scene facts:** location, activity, can they hear
- **Must address:** answers owed, commitments due now
- **Their point of view:** their memories and beliefs retrieved for this turn, plus reasons to withhold
- **Optional flavor:** thread beat or callback, may go unused

All filtering happens once, in `project`: lifecycle eligibility, who knows what, who is present, which names the
viewer knows. The prompt builder only assembles cards and stops reading `GameState` fields directly (P9).

**Per-character retrieval:** when a character speaks, the engine searches *their* memories. `@id` mentions in the
player's message (e.g. asking Uchi about Arisa → `@arisa`) boost memories that reference that character.

#### 4.3 Speaker selection and initiative (P1)
The engine picks 1-3 speakers per beat, scoring:
- whether they were addressed
- whether they are present and can hear
- interest in the topic
- how recently they spoke
- one rotating initiative bid

Each speaker has a small aim from their Mind. The storyteller writes only for the chosen speakers. Endings vary
(living-world §8): a question, an offer, an unfinished action, or a comfortable silence.

#### 4.4 Routines and availability (P7)
Routine envelopes (living-world §4): blocks by weekday and time with seeded variance, sleep as a real state, and
commitments as exceptions. At a time boundary the stepper moves characters with `world.move` and updates availability.

#### 4.5 Off-screen resolution (P4, P16)
It runs only when a turn advances time without the player witnessing it (sleep, time skip, travel). The steps:
1. Step routines chronologically through the interval.
2. List feasible encounters: same place, both awake, long enough.
3. For each encounter, build a small outcome set: nothing, talk, activity, conflict, affection, a plan, or passing on a fact. Weight it by edges, aims and threads.
4. Score it with at most one bounded Jev call per interval (zero-call authored fallback) and make a seeded draw.
5. Commit the outcomes as events, edge deltas, **memories for the participants only**, and visible traces.

A departure goes through `cast_lifecycle` `committed_intent`.

#### 4.6 Threads and commitments (P2, P15)
Threads carry milestones on the clock and advance whether or not the player helps. Their outcomes are committed
events. Commitments are memories with `due`: when one comes due, it enters that character's **must address** lane. If
no commitment exists, nothing is invented (no covered plate without a promise).

#### 4.7 Contact channel (P3)
When apart from the player, an available character may text or call, driven by commitments, threads or edge strength.
Messages are delivered on the player's next turn, because the clock is turn-based. A contact is also a memory for the
sender.

#### 4.8 Gossip (P4, P10)
A fact spreads only when an encounter or on-screen conversation passes it on, as a `told_by` memory. No cast-wide
knowledge updates.

### 5. Persistence and migration

- Save `world.where`, events, characters, relationships and memories. Rebuild `world.contents` on load.
- Migrate existing saves in stages:
  - `character_locations` → `where`
  - focal `emotion`/`relationship` → the focal character's Mind and edge
  - `BeliefState` claims and canonical `known_by` → memories
  - session chunks → `told_by`/`witnessed` memories with an unknown audience flagged
- Replace one area at a time behind the existing prompt contract, with golden-prompt tests, while the game keeps working.
- Delete dead stores once nothing reads them (P13): `epistemic_log`, `observation_log`, the unread `extracted_chunks`
  repo, dead `prompt_builder` sections.

### 6. Build order (Terrace first, generic always)

| Step | Delivers | Solves |
|---|---|---|
| 0 | ✅ Done `926bafe`: fix the lore namespace filter (BL-26); session memory keeps half the retrieval slots | P6 now |
| 1 | Character object + `world.where/contents` + `move()` + `project()`; availability state; per-character mood/relationship | P7 (availability), P8, P9, P14 (foundation) |
| 2 | Per-character memory (events, memories, provenance, `@id` refs) and per-speaker retrieval; delete dead stores | P6 permanently, P8, P10, P11, P12, P13 |
| 3 | Routines + world stepper (availability changes over time) | P7 |
| 4 | Speaker selection + initiative + varied endings | P1 |
| 5 | Threads + commitments | P2, P15 |
| 6 | Off-screen resolution + NPC↔NPC edges + gossip | P4, P16 |
| 7 | Contact channel | P3 |
| 8 | Evidence ecology for mysteries | P12, P14 fully |

Each step needs:
- tests written first
- a live check across several rosters, including a sleep/time-skip scenario where consequences appear only in prose
- the hosted arena gate before prod

### 7. Open questions
- How much of a character's memory each turn's card may carry (token budget per speaker).
- Whether to build containers (§3.1) in step 1 or defer them to evidence (step 8).
- How to author routines and threads for the 17 Terrace characters with the least effort (templates per role?).

---

## Character & World Model — Implementation Plan (steps 1-8)

> **What this doc is for:** The concrete implementation plan for redesign steps 1-8 of
> [design/WORLD_MODEL.md (world model redesign)](WORLD_MODEL.md): modules, data structures, integration points, story
> data, tests, and rollout. Edit it when the plan changes during implementation; mark steps done with their commit.
>
> Date: 2026-09-25. Step 0 (BL-26) is done in `926bafe`.

### 0. Ground rules

- **Generic engine, story data drives the differences.** No story name appears in `world_model/` code. Everything
  story-specific lives in story JSON (optional sections; a story without them still works with defaults). A rare
  last-resort game-specific mechanic goes in its own story-specific module, never in `world_model/`.
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

### 1. Package layout: `backend/app/engine/world_model/`

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

### 2. Step-by-step

#### Step 1: character object, world location index, `move()`, `project()`
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

#### Step 2: per-character memory, events, per-speaker retrieval, dead-code removal
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

#### Step 3: routines and the world stepper
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

#### Step 4: speaker selection and initiative
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

#### Step 5: threads and commitments
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

#### Step 6: off-screen resolution, NPC↔NPC edges, gossip
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

#### Step 7: contact channel
- **Queuing.** `queue_contacts` runs on the interval when the character is apart from the player, awake, and either
  has a due commitment to the player or a thread milestone involving the player, or (rarely, seeded) has high
  affection (≥0.6) at most once per day.
  - It creates `ContactMessage(sender, minute, intent, kind: text|call)` and a `contact` memory for the sender.
- **Delivery.** `deliver` hands pending messages to the scene section's must-address lane: "Your phone buzzed while
  you were busy: {sender} texted — intent: {intent}. Mention it naturally and let the player respond."
  - Delivered messages are marked delivered. There's no UI log: the message only appears in prose.
- **Asleep senders never send.** Messages to an asleep player are delivered when the player wakes up.

#### Step 8: evidence
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

### 3. Integration points (exact)

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

### 4. Tests (per step, in `tests/backend/app/engine/world_model/`)

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

### 5. Verification and rollout

1. Full suite, plus deploy-gate mode (`TESTS_BLOCK_LLM_NETWORK=1`, `-m "not integration"`).
2. Local live runs with the real model:
   - Six Strangers, 3 rosters × 6 turns, including "I go to sleep" then "where is everyone?" the next morning
   - IU: inspect the closet, and a speaker check
3. Push to beta (after coordinating with the other session's gate window).
4. Hosted beta replay.
5. Prod only through `/promote-to-prod`, on user request.

### 6. Known limits (become backlog items when shipped)
- Commitment detection is heuristic (regex). An extractor-based detector is the follow-up.
- Off-screen outcomes are weighted draws, not LLM-written scenes: consequences surface through traces, memories and
  edges only.
- `epistemic_log` / `observation_log` removal is deferred until the playback tests are migrated.

### 7. As built (2026-09-25)

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


### 8. QC round 1 (2026-09-25): findings and plan

| Item | Finding (measured) | Plan |
|---|---|---|
| Opening re-narration (BL-29) | 0/12 local turn-1 replies; about 1 in 8 on hosted beta. The failure is a *near*-verbatim retelling of the opening paragraph, which `drop_repeated_lines` (exact match only) misses. | Treat narration as a repeat when its word-trigram overlap with a recent reply is at least 0.6 (at least 8 words), so `only_repeats` triggers the existing single regeneration. Test with the observed beta text. |
| BL-30 flaky playback test | 0/4 full-suite failures when idle; failures coincided with a concurrent arena gate. The legacy `LocationExtractor` maps a 429 to intent NONE, so `extract_expect_move` fails. It isn't used by the live turn pipeline. | Retry once on 429/5xx, honoring `Retry-After` / "try again in Xms" (capped at 2 s). Unit test: a 429 then a 200 gives MOVE. Close BL-30. |
| Storyteller 429s (seen in gates) | The public "story master unavailable" error is returned on the first 429; OpenAI's body says "try again in 322ms". | The same bounded retry on the storyteller call (one retry, at most 2 s), with a test. Timeouts stay BL-28. |
| Promise detection | Pattern-based. | Measure precision and recall on live dialogue first; move it to the extractor only if the numbers justify it. |
| Six Strangers Jev 0.00 | Last gate: 2 prod wins, 10 unresolved, on nearly identical releases. | Run the hosted arena gate beta (world model) vs prod as QC after the fixes. Read the per-game table, the length table and the world-model-specific failures. |

#### QC round 1 results (2026-09-25)
- **Promises:** moved to the turn extractor (`CommitmentUpdate`, rule 11), and the regex detector was deleted. Live, 6 games:
  - regex: 12 detected, of which 6 were false positives ("I'm going to be late" recorded as a promise), and 0 NPC promises
  - extractor: 24 detected, about 23 correct (one owner flip whose wording is already from the owner's side)
  - NPC "save you dinner" caught in 6 of 6 games, and meal words set the due time (dinner -> 19:00)
  - deterministic safety nets: request owner-flip ("show me" -> the doer owns it), near-duplicate dedupe
- **Re-narration:** narration with >= 0.6 trigram overlap with a recent reply now counts as a repeat, so a turn that only
  re-tells the opening triggers the single regeneration. Local turn-1 re-narration was 0 in 12 before the change.
- **429s:** `backend/app/llm/retry.py`, one bounded retry (at most 2 s, honoring Retry-After and "try again in Xms"),
  on both storyteller calls and the legacy location extractor. Closes BL-30.

---

## Living world, open investigation, and conversational initiative

Date: 2026-09-24. Status: proposed design; no runtime implementation or quality gain is claimed.

### 1. Player goal and boundaries

The player's target is an open world that behaves like a place, rather than a sequence of puzzle prompts. Two players should be able to follow different credible paths and learn different things because of where they went, whom they trusted, and when they acted. The player may combine physical observation, conversation, records, travel, waiting, and social judgment. A discovered detail is not automatically important; a character's statement is not automatically true.

The game must remain playable without highlighting every clue. Fairness comes from **multiple grounded routes to each necessary inference**, stable world rules, and natural opportunities to recover from a missed lead. It does not come from mandatory hint bubbles or a checklist that identifies the culprit.

This proposal extends [design/JEV.md (dynamic context)](JEV.md), [design/ROADMAP_NOT_BUILT.md (game design systems)](ROADMAP_NOT_BUILT.md), [design/SOCIAL_ENGINE.md (social mode)](SOCIAL_ENGINE.md), [design/WORLD_MODEL.md (atlas)](WORLD_MODEL.md), and [design/SOCIAL_ENGINE.md (cast lifecycle)](SOCIAL_ENGINE.md). The context selector currently implements broad retrieval, Jev relevance Noul judgments, one deterministic anchor, and seeded optional power sampling behind an opt-in flag. Clue pacing, NPC routines, and the conversation policy below are **not implemented**. The current world clock advances on turns and travel; `world_calendar.py` supplies day numbers and persisted pending events for cast transitions, not a general daily routine engine.

### 2. The player's points and the mechanism for each

| Player requirement | Mechanism | Authority |
| --- | --- | --- |
| Many kinds of clues, found through different play styles | Typed evidence and claim records with observation channels, prerequisites, provenance, and independent discovery routes | Story data + engine |
| Physical observation should matter | Location and object affordances; inspection resolves authored properties and records what was actually noticed or collected | Engine |
| Conversation should reveal different information | Speaker-specific knowledge, beliefs, incentives, trust, risk, and question intent; a witness may be mistaken or evasive | Engine + bounded semantic judgments + storyteller |
| Two players can take different paths | Persistent time, location, access, NPC availability, evidence handling, relationship consequences, and optional opportunity sampling | Engine |
| Clues should be subtle without becoming arbitrary | Eligibility and direct answers are deterministic; optional surfacing is probabilistic, capped, and allowed to be absent | Engine, with Jev scoring fit |
| The world should continue around the player | Daily routine templates, commitments, travel, sleep, interruptions, and scheduled events | Engine |
| Characters feel alive and engage the player | Each present NPC has a current activity, immediate conversational aim, and initiative budget; dialogue reacts to the player's actual words | Engine packet + storyteller |
| Terrace conversations need a gentle next-turn opening | Natural conversational handoffs: a question, offer, interruption, shared activity, observable reaction, or a comfortable pause | Storyteller under a varied ending policy |
| The model must not invent facts or teleport people | A narrow authorized context packet, structured proposals, validation, and committed-state replay | Engine; Jev/LLM never own canon |

### 3. An evidence ecology, rather than a pile of clue text

Author a **case graph** of questions, claims, events, objects, people, places, and possible inferences. Each evidence record has a stable ID; kind; source and timestamp; physical or social location; visibility; owner; durability/decay; prerequisites; what the player can observe; what each speaker believes or is willing to say; and a claim or event it can support or contradict. Store `observed`, `collected`, `heard`, `verified`, and `inferred` separately. The UI may show the player's notes and provenance, never engine-only motive fields.

Clue families to support across stories:

1. **Physical traces:** damage, fibers, residue, object placement, missing items, wear, temperature, and sounds. Observation may depend on light, access, tool, and time.
2. **Documents and digital records:** receipts, schedules, messages, access logs, photographs, edits, and metadata. Access and authenticity are separate.
3. **Witness accounts:** a remembered sight, sound, time, or conversation, with source reliability and memory limits.
4. **Behavioral observations:** a pause, avoidance, habit change, or repeated visit. These are observations, not certified motives.
5. **Social-network clues:** who knows whom, who vouched for whom, and who changed an account after talking to somebody.
6. **Temporal and geographic clues:** route duration, opening hours, sleep/wake time, travel opportunity, and an alibi's feasible window.
7. **Absences and inconsistencies:** a missing item, a log gap, two accounts that disagree, or a claim incompatible with an established event.
8. **Voluntary disclosures:** confidences, admissions, promises, and explanations that may be partial or self-serving.
9. **Indirect consequences:** a cleaned room, a person arriving late, an invitation withdrawn, or a witness becoming cautious after the player shows evidence.
10. **Ordinary detail:** stable background texture that may be useful later but is not secretly treated as an omnipresent clue.

These are **types**, not ten mandatory clues per case. Author enough instances that the same inference can be approached through different modes of play. For a required inference, design at least two independent discovery routes, preferably from different families; test reachability after reasonable delays and missed opportunities. Some leads can expire, but a single missed roll must not make the central case impossible. False leads need a grounded cause: mistaken memory, a real but irrelevant trace, deliberate deception, or misinterpretation. Random generation may choose among authored eligible surfaces; it may not create evidence to justify a predetermined twist.

Example using the beta playthrough: a closet scratch and fabric scrap become two physical records. A player might compare fabric to a known garment, ask a cleaner about a damaged jacket, inspect a dated photo, or pursue the access log instead. The engine records which route was actually used. It does not label the scrap “the murder clue” in the journal.

One case inference could be “somebody entered the apartment after the reported departure.” Player A notices the scratch, finds the relevant access-log gap, and tests the route timing. Player B never enters the closet; they earn a cleaner's testimony, see a timestamped photo, and catch a witness revising their account. Both can form the inference without receiving the same staged hint. The inference is still a player conclusion until the world supplies stronger proof. The engine can record that these paths support the same question without telling the storyteller to announce it.

### 4. World time, routines, and autonomous behavior

Use the existing absolute world minute and atlas travel graph. Time advances when the player acts, travels, waits, or explicitly skips. Resolve elapsed intervals in chronological order, including sleep boundaries and events crossed during a long skip. This keeps a coherent clock without requiring the server to simulate every idle real-world minute.

Each NPC receives an authored **routine envelope**, not a rigid scene script:

- Normal activity blocks by weekday/time (work, commuting, meals, social time, sleep), with candidate locations and travel constraints.
- Exceptions: appointments, promises, emergencies, temporary access changes, and player-caused commitments.
- Private preferences and constraints: willingness to talk, need for solitude, fatigue, trust, risk, and what they know.
- A current plan plus next planned transition, persisted for replay.

At a schedule boundary, code constructs only feasible actions: continue, travel to a reachable place, keep a commitment, contact someone, rest, sleep, or choose `NONE`. Jev can score a **small feasible set** for contextual fit where semantics matter; code applies a seeded draw and revalidates capacity, travel time, access, and commitments. This is an optional scene-boundary operation, not one Jev call per NPC per chat turn. If Jev is unavailable, a deterministic policy uses authored priorities. The storyteller describes the resulting state; it does not decide where every NPC happens to be.

NPC-to-NPC interactions also need durable effects, but only at relevant event boundaries: two housemates who share a meal can exchange a permitted fact, form a plan, quarrel, or do nothing. The engine records who actually heard what. A later rumor spreads through a valid contact, not through an omniscient cast-wide memory update. When the player enters mid-conversation, the scene may reveal only its audible surface; the private cause remains private.

Sleep is a real availability state. Sleeping NPCs do not casually answer or appear elsewhere. The player may wake someone if the location and relationship permit, with an appropriate response and fatigue consequence. A late message or phone call can be unanswered, delayed, or answered by a willing awake character. Nobody should be declared “out” solely because the prose needs an empty room. On arrival, use the current location index and schedule result to tell the player who is actually there.

Avoid a metronomic world: routine envelopes allow plausible variance in departure time and activity choice, seeded per session/day and bounded by commitments. The player can learn patterns, yet an NPC can be delayed for a real reason. Persist the sampled plan and resulting events so save/resume, retry, and investigation of an alibi agree.

### 5. One turn, with clear ownership of truth

1. **Interpret the player action.** The existing structured extractor proposes movement and several state signals. Extend its typed output to capture interaction targets, speech acts, inspection, collection, and the time period named in a question. A bounded Jev decision may help classify ambiguity (question about the past versus tonight; invitation versus commitment; inspection versus collection). Preserve an ambiguous request when it cannot be resolved.
2. **Validate and advance.** Code checks the world graph, access, time cost, inventory/evidence handling, and who can hear the action. The clock and queued events advance; routines update locations and availability.
3. **Resolve earned discoveries.** Direct inspection of a valid object or a permitted direct question retrieves the corresponding authorized record deterministically. Jev may find a semantic match among records, but a low score cannot hide an earned answer.
4. **Select optional context.** Reuse broad source-balanced recall and Jev relevance judgments, then filter by visibility, cast, time, provenance, repetition, and token budget. The seeded sampler may offer a natural clue or callback, including no offer. Keep this separate from required answers.
5. **Build the storyteller packet.** Supply what the speaker can know and say, the player's observable scene, validated action outcomes, and a small set of optional opportunities. Include source IDs in internal metadata.
6. **Generate the scene.** The OpenAI storyteller produces attributed speech and narration, with a permitted conversational handoff. Its output is presentation, not an authority to mutate canon.
7. **Validate and commit.** Check speaker presence, fact IDs, allowed disclosure, travel, time, player agency, and formatting. Reject unsupported state changes; repair or regenerate with a smaller packet if necessary. Persist only accepted discoveries and statements, including their exact source and turn.

The current code already has a structured pre-render extractor, a prompt builder, and a post-response pipeline. This design adds typed evidence, routine resolution, a selected packet contract, and validation at those seams. It does not require an unbounded “director” model making every world decision.

### 6. What goes into context, and what must be said

Keep a stable instruction prefix where possible, followed by a compact **turn packet** with distinct lanes:

| Lane | Contents | Rule |
| --- | --- | --- |
| Scene authority | Absolute time, player location, route result, present/awake speakers, accessible objects, immediate event outcomes | Code-owned; always included |
| Direct response | The specific question/action, matched authorized records, source/provenance, permitted disclosure, explicit uncertainty | Must be answered or honestly declined |
| Speaker lens | This speaker's knowledge, beliefs, current activity, goals, relationship history, and reasons to withhold | Scoped to actual speaker; never pasted as player truth |
| Continuity | Recent accepted turns, established commitments, physical evidence handling, contradictions still open | Required only when relevant to this turn |
| Optional texture | At most a few eligible memories, observations, callbacks, or NPC initiatives with usage labels | May influence wording without being mentioned |
| Prohibitions | Specific absent people, unknown facts, impossible actions, already removed objects, and player actions not taken | Enforced in code as far as possible |

**MUST mention** means a narrow player-facing obligation, not “recite every selected clue.” It applies to: the direct result of the player's validated action; an answer the addressed speaker can provide; a material consequence of time or travel that just occurred; a hard boundary that blocks the action; or an event the player directly perceives and cannot reasonably miss. A sleeping witness's non-answer, a locked office, or a lost appointment belongs here. An eligible background clue, a relationship callback, and a character's unspoken motive do not.

Give each optional item a usage label (`background_constraint`, `optional_observation`, `optional_callback`, or `required_answer`), disclosure ceiling, valid channel, source ID, and repetition cooldown. The storyteller may use zero optional cues. A high Jev relevance score means “useful for this response,” not “true,” “important to the mystery,” or “must appear.” Never inject the full hidden culprit explanation into the writer and hope a prompt will suppress it.

### 7. Probability with fairness and replay

There are three different probabilities:

1. **World variance:** whether an NPC takes one of several feasible routine actions or whether a contingent event occurs. Never randomize fixed culprit/canon facts or previously committed events.
2. **Jev judgment:** whether a candidate is relevant, a conversational move is natural, or two claims address the same issue. Jev's Noul is a yes-probability for its specific rubric, not a general confidence in truth.
3. **Presentation selection:** whether an eligible optional cue is surfaced now. Code applies quality floors, cooldowns, caps, and the existing power-sampling exponent; a scene may remain quiet.

Record independent RNG streams for routines, optional clues, and conversation initiative. Seed by session, turn or scene, and policy version; persist the chosen result and scores. On retry, reuse the chosen packet. Calibrate thresholds against human-rated scenes and actual player paths, rather than treating a model probability as a tuned game rate. The current [dynamic-context design](JEV.md) already proposes a gradually rising, capped chance for unsolicited investigative cues and a deterministic direct-answer lane; use that policy instead of a second competing clue formula.

### 8. Terrace: a conversation beat that invites another turn

For a social scene, the packet should state: who is present, what each person is doing now, the player's exact speech act, recent shared history, current relationship stance, a near-term commitment or schedule boundary, and one or two feasible activities. Do not preload everyone’s private thoughts. The storyteller's beat should:

1. Respond to the player's actual words or action first.
2. Let a character pursue a small current aim (finish dinner, ask for help, avoid a topic, invite a walk, apologize).
3. Allow another present person to react only when they plausibly heard or saw it.
4. End on an **available human opening** when one naturally exists.

An opening can be a sincere question, an offer, a disagreement, an unfinished action, someone entering or leaving, a detail the player can inspect, or a comfortable silence. The engine tracks recent ending forms and downweights repetition. There is no required question every turn and no generic “What do you do next?” line. If the player asks for privacy or ends a conversation, respect it. A character can ask an actual question whose answer affects their next action, then remember the answer. Initiative is bounded: one principal new bid per beat unless the player triggered a group exchange; no forced romance, confession, or cliffhanger.

Example: the player says they came home late and missed dinner. A housemate who promised to save food may point to a covered plate and ask, “Want me to heat it, or do you need a minute?” If no promise exists, no plate should materialize to create a warm moment. A tired housemate could simply say goodnight and go to bed. Both endings give the player a real social situation to respond to.

### 9. Preventing hallucination and accidental spoilers

- **Schema is transport, not truth.** Use strict structured outputs for proposals and attributed dialogue segments where the chosen OpenAI model supports them, but validate IDs, transitions, and claims in code. Schema adherence does not establish factual correctness.
- **Separate records by epistemic status.** Canon, observed physical fact, attributed testimony, character belief, and player inference have different fields and display rules. A witness can lie; the engine records the lie as their statement without changing canon.
- **Project only allowed surfaces.** The storyteller gets “red fibers on a hinge” if observed, never the engine's hidden “this links suspect X to the murder” field. Journal and recap use the same player-visible projection.
- **Keep closed rosters and presence authoritative.** The current prompt already guards active cast and whereabouts; the schedule resolver must update that state before the scene is generated.
- **Validate material claims.** Deterministic checks reject unknown location/object/person IDs, impossible co-presence, unsupported collection, and disclosure outside permission. A targeted semantic check can inspect high-risk implicit spoilers or contradictions; it cannot guarantee perfect prose. One bounded repair/retry is preferable to silently accepting an invented clue.
- **Tie authoring and testing together.** Every essential inference needs reachable routes; every misleading lead needs provenance; every generated statement that changes play needs a source or validated event. Retest after model or prompt changes.

### 10. Build order and proof

1. **Evidence state and player projection:** typed records, discovery states, source IDs, journal filtering, and save/resume. Fix the observed beta problem where the Journal reveals private suspect goals yet omits the player's fabric scrap and scratch.
2. **Routine resolver:** schedule envelopes, sleep, travel, commitments, event order, and persisted location plans. Prove scene presence after travel and long time skips.
3. **Turn packet and direct-answer contract:** distinguish required response from optional context; ground physical inspection and questions in valid records; block unsupported evidence.
4. **Conversation initiative:** speaker aims, handoff variety, questions that affect later state, and recent-ending cooldowns; pilot in Terrace before broad rollout.
5. **Optional opportunity policy:** add clue/callback pacing and Jev semantic scoring behind the current task flag and fallback path; evaluate against the deterministic baseline.

Test with identical starting snapshots and multiple player strategies, not just a scripted “correct” path. Required checks: clue reachability through at least two paths; no private-goal journal leaks; no absent or sleeping speaker; consistent alibis across save/resume and time skips; physical evidence never invented or duplicated; direct questions answered within speaker knowledge; distinct Terrace voices; varied endings; and quiet scenes that remain satisfying. Compare full-session human judgments of agency, naturalness, surprise, and frustration. The existing arena is advisory until its human calibration and reply-length bias are addressed, so do not optimize this design solely to its current win rate.

### 11. External model contracts checked

- [TypeSafe Noul documentation](https://docs.typesafe.ai/primitives/noul): Noul answers a concrete yes/no rubric with a value from 0 to 1; criteria use true/false descriptions. Thresholding and policy remain code-owned.
- [Official OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs): strict schema adherence is available for supported models; refusals and incomplete responses still need handling. This motivates typed proposals and explicit validation, not a claim that structured text is true.

This is a design proposal. It does not assert that the schedule engine, evidence graph, dialogue handoff policy, or post-response semantic validation currently exists.

### 12. NPC behavior addendum: owner decisions (2026-09-24)

Status: design decisions; nothing below is implemented.

**Decisions**

1. **Full off-screen autonomy.** "Off-screen" means any world time the player does not witness: sleep, time skips, travel, or time spent elsewhere. During it, NPCs may start relationships, argue, make plans, and commit to leaving, driven by the world clock. The player has no control over it. Consequences persist and change later scenes.
2. **No log UI.** There is never a house log, event feed or journal of off-screen happenings. The player learns only through the story: someone mentions it, a consequence is visible ("Hikaru and Yuto aren't speaking at breakfast"), a conversation is overheard, or they never learn it. Off-screen results are engine facts with per-character knowledge (§4 "records who actually heard what"), never player-facing summaries.
3. **Generic first.** Every mechanism is engine code plus story data and works in every story. One routine resolver serves housemate schedules and suspect alibis. One off-screen resolver serves a housemate romance and suspects coordinating a story. Nothing is Terrace-specific unless it is authored data.

**Turn-based time, never real time.** The game clock advances only when the player takes a turn: each message adds its minutes, travel adds route time, and sleep or an explicit skip adds the whole span in that one turn. Closing the app freezes the world; no server process advances any session in real time, and real-world absence never produces game events. One player turn can cover hours of game time. "I go to sleep" takes about a second for the player but can advance eight in-game hours, and the NPCs may produce eight hours of change: whatever awake characters would plausibly do in that span, while sleeping characters take no part in the hours they sleep through. The amount of change scales only with game minutes elapsed.

**Off-screen resolution.** It runs only when a time interval passes without the player (§4's schedule boundaries), never on each chat turn. The steps: (1) the routine resolver moves every NPC through the interval in chronological order; (2) code lists the feasible co-presence encounters (who shared a place, awake, for long enough); (3) for each encounter, code builds a small feasible outcome set (nothing, conversation, a shared activity, conflict, an exchange of affection, a plan or commitment, or a fact passing between the two) weighted by relationship state, current aims and personal threads; (4) Jev optionally scores the set, with about one bounded call per interval and an authored-priority fallback at zero calls, and a seeded draw picks the outcome; (5) the results are committed as events, relationship-edge updates, knowledge records for the participants only, and visible traces (a changed seating pattern, a new plan, someone gone to bed early). A departure decision goes through the existing cast-lifecycle `committed_intent` path.

**Extra layers beyond §4 and §8**

- **Speaker selection (engine-owned):** 1-3 speakers per beat, chosen by who was addressed, who is present and can hear, interest in the topic, recency and one rotating initiative bid. This replaces model-chosen roll calls (BACKLOG BL-22).
- **Personal threads:** each character has 2-3 authored threads (an audition, a job decision, and in a mystery a cover story under strain) with time-based milestones. They advance whether or not the player helps, and outcomes persist.
- **Reaching out:** when apart from the player, an NPC may contact them by message or call, subject to availability and relationship. A generic channel, not a feed.
- **NPC-to-NPC relationship edges** are a prerequisite for off-screen outcomes (BACKLOG BL-11).

**Build order** (replaces §10 for social stories; evidence work from §10.1 follows for mysteries): (1) routine resolver and availability (BL-24); (2) speaker selection with conversation initiative (§8); (3) personal threads and commitment memory; (4) off-screen resolution with NPC-to-NPC edges and knowledge propagation; (5) contact channel; (6) evidence ecology (§3). Each step needs a live multi-roster check and arena comparison, and a sleep or time-skip scenario proving that consequences appear only through prose.

---

## Reusable world atlas

The atlas is a view of the same locations and routes the game uses. Artwork is
an illustrated overview; typed data remains the authority for relative distances,
place identity, grouping, provenance, and travel costs.

### Model and integration

- `world/map_model.py`: immutable `MapPoint`, `PlaceResearch`, `MapArea`, and
  `WorldMap`. Areas are non-visitable containers with optional parent areas.
  Locations remain atomic `Location` graph nodes and retain their existing IDs.
- Regional positions are schematic kilometers east (+x) and north (+y) from an
  authored origin. They are deliberately not latitude/longitude or private
  addresses. Interior positions use separate 0–100 layout coordinates per area.
- Distance bands and positions are validated together. The loader rejects
  duplicate areas, parent cycles, missing parents, invalid interior positions,
  unknown location areas, and non-finite coordinates.
- Both `WorldLoader` and `WorldDefinitionLoader` parse the same optional metadata.
  Worlds without it retain their original routing and image-only map behavior.
- `world_map_payload()` serializes the graph for both `/api/story/{id}` and
  in-session `[MAP]` responses. `PathEdge` carries travel mode and estimate status.
- `route_policy: shortest_time` opts into deterministic Dijkstra routing by
  minutes. Blocked and disconnected routes are rejected; no random short trip is
  fabricated to bridge an island. Legacy worlds keep their original policy.
- `frontend/world-map.js` renders artwork, regional and nearby views, per-area
  interiors, searchable locations, evidence status, and route previews. It has
  no Six Strangers venue list or hard-coded story IDs. SVG coordinates preserve
  equal scale on both axes; numbered markers avoid overlapping labels.
- The backend explicitly serves the component's JS/CSS at root and `/beta/`.
  Image URLs use an asset revision from metadata to refresh replaced artwork.

### Six Strangers research decisions

`documentation/research/terrace_house_bgitc_places.md` and the accompanying chart
are preserved user research. `scripts/build_six_strangers_world.py` reproducibly
compiles this inventory into the world JSON; it does not execute document text.

The distance table takes precedence over overlapping chart labels. Its cluster
directions and distance bands are retained as approximate local offsets. No
uncertain venue is assigned an invented address. Nakameguro and the salon's
regional placement are explicitly approximate; unnamed venues have no map point.

The world contains 103 visitable places, 25 region/venue containers, and 270
directed edges (135 bidirectional links). All H01–H18, E01–E67 and O01–O15
inventory IDs are represented. O13 points to H15, the house swimming pool, so it
does not create a duplicate location. Four existing game additions remain: the
gender-matched shared bedrooms, neighborhood streets, Gotanda Station and fictional local cafe.
Existing location IDs, including `terrace`, `salon`, and `dance_studio`, stay
stable for character positions and saved sessions.

The functional house layout adds playroom, washitsu, separate bath/vanity/toilet/
laundry, hallway, pool, barbecue and driveway. `terrace` now means the pool deck
beside the living/dining glazing, not a rooftop. Related story prose is aligned.

Travel times are explicitly **gameplay estimates**, separate from researched
straight-line distances. Regional arrivals go to individual venues; interior
areas such as museum workshops, backstage rooms and the mountain summit are
reached through their associated front/public area. Unknown venues use labeled
estimated transit connections, not claims of proximity. The travel engine still
adds its configured departure cost to the route's transit minutes.

Historical names and episode evidence are research labels, not claims of current
business operation or a script that automatically reenacts future episodes.
O14/O15 and similar broad scene types remain generic placeholders because the
supplied research cannot identify every distinct establishment or private room.

### Artwork and verification

The redesigned Japanese RPG-style regional atlas is stored at the game's existing
`7_six_strangers.png` path. It has an enlarged house inset and an off-map Nagatoro
inset. Regional illustration distances are compressed; the data views provide the
faithful equal-scale relationships. Native generated resolution is 1536×1024;
two requests for higher native resolution did not change the generator's output.
No interpolated upscale is represented as additional detail. The generation
prompt is preserved in `documentation/research/six_strangers_artwork_prompt.md`.

Regression tests cover research coverage/deduplication, distance bands and
directions, reachability, blocked/shortest routes, both loaders, legacy IU loading,
API payloads, asset serving and frontend wiring. The location extractor no longer
truncates its destination list at 80 nodes.

`scripts/verify_world_map_browser.py --url <site> --output <artifact-directory>`
exercises the actual game UI with Chromium desktop and iPhone 13 WebKit, including
onboarding, artwork loading, region filtering, search, route details, interior
selection, enlargement, closing/reopening, JS errors and API request hosts.
Install optional Playwright tooling in the `storieschat` environment to run it.

### Player-facing map presentation (2026-09-24)

Startup and resume display only the clickable artwork. Tapping it opens the
full-screen image; double-tapping or pinching zooms it, and a zoomed image can
be dragged. The map menu or `[M]`/`[MAP]` command
opens the optional location browser. Descriptions are brief room/venue purposes;
research status, episode references and internal geometry notes stay out of the
player UI. Source research remains available in authored metadata. The world
builder generates the same short descriptions as the committed world JSON.
