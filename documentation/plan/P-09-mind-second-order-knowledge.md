---
id: P-09
title: The mind - what I know, what I think you know and feel, with fog of war
stage: 2
size: L
depends_on: [P-08]
touches: [backend/app/engine/world_model/mind.py, backend/app/engine/world_model/epistemics.py, backend/app/engine/world_model/memory.py, backend/app/engine/world_model/gossip.py, backend/app/engine/world_model/person.py, backend/app/engine/world_model/signals.py]
backlog: BL-85 (P3), BL-72, BL-83 (a), BL-24 (last seen)
---
**Goal:** each character keeps, in the saved world state, first-order knowledge (existing) and second-order beliefs: "I
think X knows P", "I think X feels F toward me", and the last place and time they saw or heard of every other person. Nobody
knows where anyone is, or what they did, without perceiving it or being told.

**Read first:** `documentation/backlog/BL-85-character-social-mind.md` (sections 3 and 6, owner decision: fog of war), `world_model/epistemics.py`
(`observe_event`, `transmit`), `memory.py`, `gossip.py`, `persona.py`, `signals.py`, `BL-72` in
`documentation/backlog/BL-72-73-74-terrace-gameplay-loop-findings.md`, `design/CHARACTER_MEMORY.md`.

**Build**
- `ThinksKnows(owner, other, proposition, basis)` and `ThinksFeels(owner, other, feeling, basis, confidence)` entries,
  created only through the existing perception path with evidence (I told X; I saw X present when it was said; someone told
  me they told X). The basis, or its absence ("X was not there when I learned P"), is stored. Affinity signals are recorded as
  the observer's ambiguous perception, so a misread is possible.
- Last-seen record per person (place, minute); "where is Yuriko?" and the player's `(find Arisa)` read **the asker's** mind
  plus routines they know, never `world.place_of` (BL-72). Searching can miss.
- Claims carry the teller's intent (sincere, exaggerated, false, staged); gossip keeps the tag; a false rumour stays false
  in the engine however far it spreads (BL-83 a).
- Derived, disclosure-safe scene facts: secret held, dramatic irony, exposure risk, misread (used by P-11; engine truth is
  never written into a prompt).

**Tests first (no-telepathy):** remove a witness and the belief disappears; change a hidden feeling and nobody's mind changes;
a character absent for an event does not learn it; "where is X" answers from last seen and can be stale; a false rumour stays
false. Old saves load. **Arena gate** before any prompt-visible change.

**Done when:** suite green; `CHARACTER_MEMORY.md` and `SOCIAL_ENGINE.md` updated; BL-85 P3, BL-72 (the player-facing way to find
a housemate; keep a smaller remainder if the UI part is separate) and BL-83 (a) removed or narrowed in the same commit.
