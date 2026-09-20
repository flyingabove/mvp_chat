# Cast Lifecycle Design

> **What this doc is for:** Defines the reusable, story-authored system for games whose recurring characters enter, leave, or temporarily become unavailable. Edit this document when lifecycle states, slot rules, transition validation, prompt eligibility, persistence, or player-facing roster behavior changes.

## 1. Goal and boundary

The engine needs to support a stable catalog of authored characters while only a
subset participates in the current world. Six Strangers is the first consumer:
the source format keeps six NPC residents in three men and three women slots,
then fills a vacated slot with the next eligible resident from the same group.

The engine vocabulary is deliberately generic. It knows `slot_groups`,
capacities, membership status, transition events, and replacement policies. It
does not know gender, a house, television seasons, eliminations, or Terrace
House. Another story can use the same system for a rotating expedition crew,
school cohort, sports lineup, workplace team, or political cabinet.

Lifecycle changes are world-state changes. Only engine validation may apply
them. A narrated departure without an applied transition does not remove a
character; an upcoming character mentioned by name does not become active.

## 2. Static authoring schema

Stories opt in with a top-level `cast_lifecycle` object:

```json
{
  "cast_lifecycle": {
    "enabled": true,
    "arrival_location_id": "front_entry",
    "replacement_policy": "same_slot_next",
    "departure_policy": "committed_intent",
    "slot_groups": {
      "men": {"capacity": 3, "label": "Men's resident slots"},
      "women": {"capacity": 3, "label": "Women's resident slots"}
    },
    "members": {
      "makoto": {"slot_group": "men", "initial_status": "active", "sequence": 0},
      "arman": {"slot_group": "men", "initial_status": "upcoming", "sequence": 1}
    }
  }
}
```

Rules:

- Every lifecycle member key must match one `characters[].key`.
- Every referenced slot group must exist and have a positive capacity.
- Initial active membership cannot exceed a group's capacity.
- Sequence values must be non-negative integers and unique within a group.
- `arrival_location_id` must exist in the story world.
- Stories without this object behave exactly as they do today: every authored
  character is active and scene-eligible.
- The authored character catalog contains identity and private knowledge for
  all potential members. Lifecycle status determines whether any of it may
  enter a prompt or player-visible output.

## 3. Runtime model

`GameState.cast_lifecycle` holds a `CastLifecycleState` when the story opts in.

### Statuses

| Status | Meaning | Scene eligible | May become active |
|---|---|---:|---:|
| `upcoming` | Authored but has never joined this run | no | yes |
| `active` | Current participant/resident | yes | already active |
| `inactive` | Temporarily unavailable, with accumulated state retained | no | yes |
| `departed` | Permanently left under current story rules | no | no by default |

Each member runtime record contains:

- `status`
- `slot_group`
- `sequence`
- `activated_minute`
- `departed_minute`
- `departure_reason`

The lifecycle also stores append-only transition history. Each record contains
an event id, event type, departing member if any, arriving member if any,
vacated slot group, reason summary, minute, and resulting statuses. Event ids
make retries idempotent.

## 4. Validated operations

The lifecycle module is a pure domain service with primitive JSON round trips:

- `active_ids(slot_group=None)`
- `is_scene_eligible(character_id)`
- `vacancies(slot_group)`
- `next_up(slot_group)`
- `activate(character_id, minute)`
- `deactivate(character_id, minute, reason)`
- `depart(character_id, minute, reason)`
- `replace(departing_id, arriving_id=None, minute, reason, event_id)`

`replace` validates the complete change before mutating anything:

1. Lifecycle is enabled and the event id has not already been applied.
2. Departing member exists and is active.
3. The member's slot group exists.
4. The requested arrival is upcoming, belongs to the same slot group, and does
   not violate capacity; otherwise choose the lowest-sequence eligible member
   when policy is `same_slot_next`.
5. Arrival location exists.

After domain validation, the API integration helper removes the old member's
runtime location and transient markers, places the replacement at the authored
arrival location, and changes the focal character if the prior focal member
departed. Relationship and epistemic history are retained rather than deleted.

## 5. Trigger policy

The authored interactive policy is `committed_intent`:

- A resident can discuss uncertainty without triggering departure.
- A player cannot evict an NPC through ordinary dialogue.
- The lifecycle domain and API integration helper are implemented and tested.
- Automatic prose-to-transition extraction is the next integration phase. It
  must propose a departure only when the previous assistant reply contains a
  clear first-person commitment to leave, and may apply at most one event per
  turn.
- Replacement selection is deterministic story data; arrival can occur in the
  same transition response or after an authored vacancy beat, according to the
  story's configured timing policy.

The lifecycle service does not parse prose. Future authored schedules, quest
rewards, administrator tools, or simulations must call the same validated
operations rather than adding alternative mutation paths.

## 6. Prompt and knowledge eligibility

Lifecycle filtering is defense in depth:

- Character mention detection ignores upcoming, inactive, and departed members.
- People-present calculation includes only active members at the current
  location.
- On-call and scene speaker markers for ineligible members are ignored and
  cleared during transitions.
- Identity, belief, private fact, relationship, room-dynamics, and scene-cast
  prompt layers include only active characters unless a dedicated historical
  reference explicitly requests departed public information.
- Upcoming names and biographies never appear in player-visible cast output.
- The character graph retains all nodes and accumulated edges; rendering filters
  by eligibility.
- The turn extractor's `allowed_character_keys` catalog
  (`prompt_engine.py`'s `character_key_to_name`) is filtered through the same
  `_cast_scene_eligible` predicate before being sent to the LLM-backed
  extractor — an upcoming/departed character's key and real name are not
  handed to the extractor as a candidate, matching every other eligibility
  gate in this section (2026-09-19 fix; previously this one call site built
  the catalog from the full unfiltered roster).
- A canonical fact whose *only* `known_by` owner is a still-`upcoming`
  character (e.g. that character's private concern/biography) is excluded
  from both `_knowledge_chunks_from_state` and `_canonical_facts_for_speaker`
  in `prompt_builder.py`, even if something in the scene would otherwise
  surface it as "known by" the speaker. Facts shared with `all`/
  `all_characters`, or owned by at least one already-active character, are
  unaffected. Departed characters' facts remain visible to characters who
  already knew them — this filter only blocks a character who has *never yet
  arrived* from leaking their private facts early.

The authored `is_main` flag remains a starting preference, not permanent
membership. If that member departs, the runtime focal moves to the replacement,
or to the deterministic first active character when the queue is empty. Static
authoring flags are not mutated.

For a lifecycle-enabled story, the main character's identity block
(`_character_identity_section`) and "focal lens" framing
(`_storyteller_scene_section`'s scene brief) are now also gated on the main
character actually being present in the current scene
(`_main_character_scene_eligible`, `prompt_builder.py`), not injected
unconditionally. Non-lifecycle stories are unaffected — they keep the legacy
always-inject-main behavior (an always-present ghost/narrator NPC not tied to
a location remains supported). This fixes the audit-reported bug where an
explicit solitary scene ("I go to the rooftop alone") still had the focal NPC
narrated as present, because the identity/framing layers ignored scene
presence entirely for the main character.

## 7. Persistence and compatibility

State JSON adds `cast_lifecycle`. The existing `main_character_id` acts as the
runtime focal pointer; restore replaces it when its member is no longer active.

No database schema migration is required because session state is stored as
JSON. Restore rules:

- A saved lifecycle snapshot is authoritative; later edits to queue order do not
  rewind a run.
- Saved snapshots validate against their recorded members and history. Catalog
  reconciliation for characters added after a save is a future schema migration
  and is intentionally not implicit.
- A lifecycle-enabled story save created before this feature initializes from
  current authoring: the original configured cast is active and the rest are
  upcoming.
- Stories without lifecycle configuration treat all characters as active.
- Unknown saved ids remain in the snapshot for audit/history but are never scene
  eligible if the current story no longer authors them.

## 8. Player-facing roster

A read-only cast view may show:

- current active residents the player has met,
- vacant slot labels,
- departed residents the player previously met.

It never reveals upcoming members or queue order. The normal player interface
does not include an eviction control. If a story later allows player-managed
lineups, that is an explicit story policy using the same validated transition
service.

## 9. Six Strangers rules profile

The supplied Boys & Girls in the City dossier establishes these format rules:

1. Six NPC residents are active: three men and three women.
2. They share a furnished Tokyo house and coordinate two shared cars.
3. They continue outside jobs, school, training, creative work, friendships,
   and dates.
4. There are no imposed challenges, eliminations, prize, fixed romance, or win
   condition.
5. Cooking, chores, work, outings, quiet time, friendship, and romance emerge
   from choices. Invitations and affection require consent.
6. A resident may voluntarily leave after clearly deciding they are ready; no
   vote, failure, or romantic outcome is required.
7. One new resident fills the vacated same-gender slot. Arrival order follows
   the supplied season chronology; timing and every relationship remain
   emergent.
8. Housemates do not know private concerns, future entrants, or televised
   outcomes. Audience asides cannot leak that information.

The current game adds the player in a separate guest room. Whether that player
remains a permanent seventh resident or occupies a lifecycle slot is a product
decision recorded in the story's profile, not an engine assumption.

## 10. Verification contract

Implemented tests cover schema validation, initial capacity, deterministic
next-up selection, wrong-slot rejection without partial mutation, idempotent
event replay, departure/location cleanup, arrival placement, focal replacement,
state serialization, roster privacy, legacy behavior, and the full Six
Strangers invariant of 17 authored characters with six active and eleven
upcoming before any transition. The automatic committed-intent trigger and
next-day scheduler require extractor and time-boundary tests when that phase is
implemented.

Live beta verification for this phase must exercise initial roster privacy and
ordinary scene behavior. A later live pass must exercise the automatic
departure trigger, next-day replacement, and server-backed resume after that
scheduler exists.
