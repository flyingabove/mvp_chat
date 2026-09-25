# Character & World Model Redesign

> **What this doc is for:** The agreed design for a robust character object, a world-owned location index,
> events, memories and relationship edges. Together these make the game world consistent and engaging.
> Edit this doc when the data model, a mechanic, or the build order changes.
>
> Date: 2026-09-24. Status: **agreed design, not implemented.** Extends
> [LIVING_WORLD_INVESTIGATION_AND_CONVERSATION_DESIGN.md](LIVING_WORLD_INVESTIGATION_AND_CONVERSATION_DESIGN.md)
> (routines, turn packet, evidence, and the §12 owner decisions) and
> [CAST_LIFECYCLE_DESIGN.md](CAST_LIFECYCLE_DESIGN.md).

---

## 1. Problems we are solving

| # | Problem | What the player sees today | Root cause in code |
|---|---|---|---|
| P1 | **Who speaks is decided by the model** | Roll calls where 4-5 housemates talk every turn; one NPC dominates (BL-22) | No speaker-selection policy; the storyteller picks speakers freely |
| P2 | **NPCs have no lives of their own** | Nothing moves forward without the player; no arcs (e.g. Momoka's audition) | No personal-thread or milestone model |
| P3 | **NPCs never reach out** | Nobody texts or calls when apart | No contact channel as a behavior |
| P4 | **No NPC-to-NPC relationships** | Housemates have no history with each other; gossip is impossible | `character_graph` edges exist mostly player↔NPC (BL-11); NPC↔NPC state is never updated |
| P5 | **Build order was investigation-first** | Terrace needs living routines and conversation first | Living-world §10 starts with evidence |
| P6 | **Authored lore never reaches the prompt** (confirmed, BL-26) | IU answers about her life from general model knowledge, not authored facts | `retrieve_knowledge` `_filter_by_namespace` drops every authored chunk (live path: 0 of 57 IU chunks; 8 without the filter) |
| P7 | **NPCs never move** (BL-24) | Whereabouts drift from the story; nobody leaves for work or goes to bed | `character_locations` only changes on opening, arrival and departure |
| P8 | **Only the focal character has an inner life** | In group scenes, four of five speakers have no memory, mood or beliefs of their own | Mood/relationship live on `GameState` (focal only); retrieval, beliefs and knowledge filters key off `main_character_id` |
| P9 | **Character state is scattered** | Bugs where one prompt layer forgets a filter (whereabouts missing, unarrived names leaking) | One character's data spans ~10 `GameState` fields; the prompt builder stitches and filters each separately |
| P10 | **Memories have no owner or source** | NPCs "know" things they never heard; a player's claim is treated as fact | `SessionChunkStore` chunks have no speaker, no audience, no provenance |
| P11 | **Short, lossy conversation memory** | Anything older than about 3 exchanges is only loose sentences | Log trimmed to 6 rendered messages; no event records |
| P12 | **No difference between truth and perspective** | No foundation for alibis, mistaken witnesses or lies | Canonical facts and beliefs are flat text; nothing records what actually happened vs. who perceived it |
| P13 | **Dead and duplicate memory stores** | Harder to reason about; wasted code paths | `epistemic_log`, `observation_log`, `tells`, edge `narrative`/`disposition`, `extracted_chunks` table written but never read |
| P14 | **Objects and evidence have no place in the world** | Nothing to notice in a room; the mystery can't use physical clues | No entity/location model for objects |

## 2. Owner decisions (constraints on every mechanic)

1. **Turn-based clock.** Game time advances only when the player takes a turn. Closing the app freezes the world. One turn
   can cover hours (sleep = 8 hours), and awake NPCs may produce that many hours of change in one resolution step.
2. **Full off-screen autonomy.** While the player sleeps or is away, NPCs may date, fight, make plans or decide to leave.
3. **No log UI, ever.** No house log or event feed. The player learns only through the story: being told, noticing
   consequences, overhearing.
4. **Generic first.** Every mechanism is engine code plus story data and works in every story. Routines serve both
   housemate schedules and suspect alibis.
5. **The engine owns facts, the storyteller writes the scene.** The LLM never decides where people are, what happened
   or who knows what. Characters never call an LLM; they are data plus deterministic, seeded methods.

## 3. Data model

Four collections of plain data are saved with the game. Everything else is a query over them.

```
world         clock, where{entity_id -> place_id}, events[]       (contents{} is derived)
characters    identity, availability/activity, routine, mind, commitments, threads, contact
relationships from, to, trust/affection/fear/suspicion, label, impressions    (feelings only)
memories      owner, event?, text-with-@ids, refs[], source, confidence, time, due?
```

Objects and evidence are **entities** like characters: an ID, properties, and whatever can be noticed about them.

### 3.1 Location: the world owns it

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

### 3.2 Character

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

### 3.3 Relationship edges: feelings only

A directed edge `from → to` records how one character feels about another *now*: trust, affection, fear, suspicion,
a static label, and short impressions. This includes NPC↔NPC edges (P4). Edges are **not** a record of what happened;
that lives in events and memories. "Do A and B share a past?" is a query (events where both took part), not a stored
edge.

### 3.4 Events: what actually happened (world truth)

```json
{ "id": "E17", "time": "2021-06-03T19:00", "place": "yoyogi_park",
  "participants": ["a", "b"], "truth": "@a and @b argued about the money", "visibility": "private" }
```

Events come from authored backstory (for example the night of a crime), off-screen resolution, and accepted on-screen
outcomes. Once committed, an event never changes. Lies and mistakes live in memories, not events.

### 3.5 Memories: one character's perspective

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

### 3.6 Objects and evidence

An entity with an ID, a location from `world.where`, authored properties, and "noticeable" surfaces that depend on
light, access, tool and time. A character's knowledge *of* evidence is a memory ("I saw the scratch at 22:00"); the
evidence itself exists whether or not anyone knows it. Full evidence ecology: living-world doc §3.

## 4. Mechanics

### 4.1 Moving and arriving (A → B)
1. `world.move(player, B)` advances the clock by the route time; the routine stepper updates everyone for those minutes.
2. `world.contents[B]` gives the characters and objects there.
3. Each awake character reacts to the player according to their edge and meeting history (a warm greeting, a cold nod, ignoring them).
4. Speaker selection (§4.3) picks who talks; objects become things to notice or inspect.

### 4.2 Context projection: the only way character data reaches the LLM
`character.project(scene, viewer, budget)` returns lanes (living-world §6):
- **Scene facts:** location, activity, can they hear
- **Must address:** answers owed, commitments due now
- **Their point of view:** their memories and beliefs retrieved for this turn, plus reasons to withhold
- **Optional flavor:** thread beat or callback, may go unused

All filtering happens once, in `project`: lifecycle eligibility, who knows what, who is present, which names the
viewer knows. The prompt builder only assembles cards and stops reading `GameState` fields directly (P9).

**Per-character retrieval:** when a character speaks, the engine searches *their* memories. `@id` mentions in the
player's message (e.g. asking Uchi about Arisa → `@arisa`) boost memories that reference that character.

### 4.3 Speaker selection and initiative (P1)
The engine picks 1-3 speakers per beat, scoring:
- whether they were addressed
- whether they are present and can hear
- interest in the topic
- how recently they spoke
- one rotating initiative bid

Each speaker has a small aim from their Mind. The storyteller writes only for the chosen speakers. Endings vary
(living-world §8): a question, an offer, an unfinished action, or a comfortable silence.

### 4.4 Routines and availability (P7)
Routine envelopes (living-world §4): blocks by weekday and time with seeded variance, sleep as a real state, and
commitments as exceptions. At a time boundary the stepper moves characters with `world.move` and updates availability.

### 4.5 Off-screen resolution (P2, P4)
It runs only when a turn advances time without the player witnessing it (sleep, time skip, travel). The steps:
1. Step routines chronologically through the interval.
2. List feasible encounters: same place, both awake, long enough.
3. For each encounter, build a small outcome set: nothing, talk, activity, conflict, affection, a plan, or passing on a fact. Weight it by edges, aims and threads.
4. Score it with at most one bounded Jev call per interval (zero-call authored fallback) and make a seeded draw.
5. Commit the outcomes as events, edge deltas, **memories for the participants only**, and visible traces.

A departure goes through `cast_lifecycle` `committed_intent`.

### 4.6 Threads and commitments (P2)
Threads carry milestones on the clock and advance whether or not the player helps. Their outcomes are committed
events. Commitments are memories with `due`: when one comes due, it enters that character's **must address** lane. If
no commitment exists, nothing is invented (no covered plate without a promise).

### 4.7 Contact channel (P3)
When apart from the player, an available character may text or call, driven by commitments, threads or edge strength.
Messages are delivered on the player's next turn, because the clock is turn-based. A contact is also a memory for the
sender.

### 4.8 Gossip (P4, P10)
A fact spreads only when an encounter or on-screen conversation passes it on, as a `told_by` memory. No cast-wide
knowledge updates.

## 5. Persistence and migration

- Save `world.where`, events, characters, relationships and memories. Rebuild `world.contents` on load.
- Migrate existing saves in stages:
  - `character_locations` → `where`
  - focal `emotion`/`relationship` → the focal character's Mind and edge
  - `BeliefState` claims and canonical `known_by` → memories
  - session chunks → `told_by`/`witnessed` memories with an unknown audience flagged
- Replace one area at a time behind the existing prompt contract, with golden-prompt tests, while the game keeps working.
- Delete dead stores once nothing reads them (P13): `epistemic_log`, `observation_log`, the unread `extracted_chunks`
  repo, dead `prompt_builder` sections.

## 6. Build order (Terrace first, generic always)

| Step | Delivers | Solves |
|---|---|---|
| 0 | Fix the lore namespace filter as its own change, with the arena gate (BL-26) | P6 now |
| 1 | Character object + `world.where/contents` + `move()` + `project()`; per-character mood/relationship | P8, P9, P14 (foundation) |
| 2 | Per-character memory (events, memories, provenance, `@id` refs) and per-speaker retrieval; delete dead stores | P10, P11, P12, P13, P6 permanently |
| 3 | Routines + stepper + availability | P7 |
| 4 | Speaker selection + initiative + varied endings | P1 |
| 5 | Threads + commitments | P2 |
| 6 | Off-screen resolution + NPC↔NPC edges + gossip | P2, P4 |
| 7 | Contact channel | P3 |
| 8 | Evidence ecology for mysteries | P12, P14 fully |

Each step needs:
- tests written first
- a live check across several rosters, including a sleep/time-skip scenario where consequences appear only in prose
- the hosted arena gate before prod

## 7. Open questions
- How much of a character's memory each turn's card may carry (token budget per speaker).
- Whether to build containers (§3.1) in step 1 or defer them to evidence (step 8).
- How to author routines and threads for the 17 Terrace characters with the least effort (templates per role?).
