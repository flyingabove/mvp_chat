# NPC Workflow + Sidequest Design

> **What this doc is for:** Design of NPC lifecycle and sidequest trigger system. Edit this doc when NPC behavior, sidequest triggers, or quest logic changes.

Last updated: 2026-02-27

---

## Part I — Philosophy

### What is an NPC hallucination, really?

When the LLM introduces a character the author never defined — "a nervous-looking man at the end of the bar" — it isn't making an error. It's worldbuilding. The player's curiosity created a narrative need; the LLM filled it plausibly.

The engine should treat these emergent characters as **real**, persistent participants. Discarding them (letting them vanish between turns) breaks immersion and wastes the relationship information already building around them. Capturing and persisting them is the right move.

The distinction that matters is not *authored vs. hallucinated* but **shallow vs. deep**:
- A shallow NPC is a plausible detail: a name, a face, a mood. Enough to make the world feel inhabited.
- A deep NPC has motivation, secrets, a history with the player. They can anchor a sidequest.

Shallow NPCs remain shallow until the player shows interest. **Depth is earned through engagement, not pre-written.**

---

### When should backstory be generated?

Never speculatively. Backstory should only be generated when the player's actions signal genuine interest. Three signals matter:

1. **Repeated engagement** — the player has talked to the NPC multiple times (meeting_count ≥ 3). They're not just passing through.
2. **Emotional investment** — the player's attitude toward the NPC has warmed (affection ≥ 0.3 or trust ≥ 0.3 on the player→NPC edge).
3. **Direct inquiry** — the player explicitly asks about the NPC's past, motivations, or secrets.

Any one of these signals is sufficient to trigger backstory generation. The result is locked immediately — it becomes canonical for the session and cannot be contradicted by future LLM responses.

The corollary: **do not pre-generate backstory for every NPC at spawn time**. Most NPCs will remain shallow and that's fine. Pre-generation wastes tokens and creates unused content.

---

### Sidequests: authorized hallucination

The LLM should not hallucinate sidequests freely. Unauthorized sidequest generation would break narrative coherence — the author spent time crafting the main story arc, and random LLM diversions dilute it.

But **authorized sidequest hallucination** is a feature, not a bug. The conditions for authorization:

1. **Familiarity threshold** — player and NPC have met enough times (meeting_count ≥ 3) and the relationship has some warmth
2. **Narrative readiness** — a minimum number of main story turns have passed (prevents sidequests in the first 5 minutes)
3. **Player curiosity signal** — player asks about the NPC beyond surface-level conversation

When all three conditions are met, the engine can signal to the LLM that a sidequest is available for this NPC. The LLM proposes it; the engine stores it; the player decides.

Sidequests should be:
- **Small**: 3–7 turns to complete, not sprawling arcs
- **Personal**: about the specific NPC, not abstract tasks
- **Emergent**: grown from facts already established (canonical facts, relationship history)
- **Optional**: never blocking the main story

---

### The familiarity curve

Familiarity is the bridge between "stranger" and "ally with secrets." It moves slowly, which is intentional. A player who asks an NPC one question hasn't earned their backstory. A player who has spoken to them four times, learned their name, and shown warmth toward them — that player has.

```
meeting_count:  1         2         3         4+
familiarity:    "stranger" → "acquaintance" → "familiar" → "confident"
backstory:      none        none            pending       available
sidequest:      locked      locked          available     available
```

Familiarity is not stored as a single number. It is derived at query time from:
- `meeting_count` (engine-tracked on the player→NPC edge)
- `player_attitude` (`affection`, `trust` on the player→NPC edge, updated by `RelationshipStateUpdate`)

This means familiarity can grow quickly through warmth (trust/affection escalating from player's words) even with few encounters — or slowly through cold repeated meetings.

---

## Part II — Technical Architecture

### NPC as a Character subtype

The existing `CharacterType.NPC` enum value already models incidental characters. What's missing is lifecycle metadata on `Character`:

```
Character (additions needed):
  generation_source: str = "authored"
    # "authored"        — defined in story JSON
    # "llm_hallucinated" — introduced by LLM during gameplay
    # "engine_auto"     — created by engine (e.g. make_player_character)

  backstory_status: str = "none"
    # "none"       — no backstory generated yet
    # "pending"    — trigger conditions met, generation queued
    # "generated"  — backstory exists and is locked as canonical

  introduced_at_minute: Optional[int] = None
    # game minute when first mentioned (set on first add_character call)
```

These fields let the engine:
1. Track the origin of every character (author vs. runtime)
2. Know whether backstory generation has been triggered
3. Avoid re-generating backstory for the same NPC

---

### When is a hallucinated NPC captured?

The LLM is already constrained by the `previous_scene.speakers` field extracted by `TurnExtractor`. Characters mentioned in the NPC's reply are recorded as speakers. But they're not automatically added to `CharacterGraph` — they're just string keys in the scene buffer.

The capture pipeline should be:
```
1. TurnExtractor extracts previous_scene.speakers (already done)
2. prompt_engine.py: for each speaker key not in character_graph.characters:
     - Create a minimal Character(key=key, character_type=NPC,
         name=infer_name_from_reply(), generation_source="llm_hallucinated",
         introduced_at_minute=current_minute)
     - character_graph.add_character(new_npc)
     - Create player→NPC edge via process_first_meetings (already done)
3. NPC persists for the session in the character_graph
```

The name inference is simple: scan the previous assistant reply for capitalized proper nouns near the key mention.

---

### Backstory generation trigger

Called after each turn, checked per NPC:

```python
def should_generate_backstory(player_edge: RelationshipEdge, npc: Character) -> bool:
    if npc.backstory_status != "none":
        return False  # already done
    if npc.character_type != CharacterType.NPC:
        return False  # authored chars already have backstory
    meeting_count = player_edge.meeting_count
    familiarity = player_edge.state.affection + player_edge.state.trust
    return meeting_count >= 3 or familiarity >= 0.30
```

When triggered:
1. `npc.backstory_status = "pending"` immediately (prevent re-trigger)
2. A background call is made to generate a minimal NPC backstory (role, motivation, 1 secret, 1 connection to main story)
3. Result is stored as `npc.self_knowledge` entries (same field as canonical characters)
4. `npc.backstory_status = "generated"` — locked, canonical for the session

The backstory generator is given context: the main story scenario, the NPC's key, the player's current relationship state toward them, and any canonical facts already established. This ensures the backstory fits the world.

---

### Sidequest authorization

A sidequest becomes available for an NPC when:

```python
def sidequest_available(player_edge: RelationshipEdge, npc: Character, game_minute: int) -> bool:
    MIN_TURNS_BEFORE_SIDEQUEST = 10  # no sidequests in opening sequence
    if game_minute < MIN_TURNS_BEFORE_SIDEQUEST:
        return False
    if npc.backstory_status != "generated":
        return False  # must have backstory first
    familiarity = player_edge.state.trust + player_edge.state.affection
    return player_edge.meeting_count >= 3 and familiarity >= 0.20
```

When available, the engine injects a subtle signal into the NPC's system prompt:
```
[SIDEQUEST AVAILABLE]
{npc_name} has a personal matter that could use the player's help. You may
hint at it if the conversation reaches an appropriate opening. Keep it small
and personal to {npc_name}'s backstory. Do not force it — let the player ask.
```

This is authorized hallucination: the LLM knows it's allowed to propose a sidequest. It doesn't do it randomly — it waits for a natural opening. The player can ignore it.

---

### Where sidequests are stored

A sidequest, once offered and accepted, is stored in `GameState.active_sidequests` (not yet implemented — pending):

```
Sidequest:
  id: str                  # canonical key
  npc_key: str             # which NPC anchors it
  title: str               # brief label ("Help Mia find the missing letter")
  steps: List[str]         # 3-7 high-level steps
  status: str              # "offered" | "active" | "completed" | "abandoned"
  offered_at_minute: int
  completed_at_minute: Optional[int]
```

Sidequest progress is tracked via the existing epistemic/transient knowledge system — each completed step is recorded as a canonical fact (locked, not updatable). The final step completion marks the sidequest as done.

---

### Relationship between familiarity and main quest pacing

Sidequests compete with main story pacing. A design guardrail:
- No more than 1 active sidequest at a time per NPC
- Sidequests cannot interrupt a main-story "critical path" scene (flagged by author in story JSON as `locked_scene: true`)
- Sidequest content should reference and reinforce main story facts — never contradict them

The author controls the critical path lock. The engine controls sidequest eligibility timing. The LLM controls the moment of offer (within the authorized window).

---

## Implementation Order (recommended)

| Priority | Work item |
|---|---|
| 1 | Add `generation_source`, `backstory_status`, `introduced_at_minute` to `Character` |
| 2 | Capture hallucinated NPCs in `prompt_engine.py` from `previous_scene.speakers` |
| 3 | Implement `should_generate_backstory()` + minimal backstory generator |
| 4 | Implement `sidequest_available()` + prompt injection signal |
| 5 | `GameState.active_sidequests` storage + step tracking |
| 6 | Author `locked_scene` flag on story JSON critical path scenes |

Items 1–2 are prerequisites for everything else. Items 3–6 can be built incrementally.
