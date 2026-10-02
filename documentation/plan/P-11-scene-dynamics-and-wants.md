---
id: P-11
title: Scene dynamics, inner states and character wants (the core of the vision)
stage: 3
size: L
depends_on: [P-08, P-09, P-10]
touches: [backend/app/engine/world_model/scene.py, backend/app/engine/world_model/turn.py, backend/app/engine/world_model/stakes.py, backend/app/engine/world_model/signals.py, backend/app/engine/world_model/agenda.py, backend/app/engine/world_model/person.py, backend/app/engine/prompt_builder.py]
backlog: BL-85 (P4), BL-84 (group energy, third-party reads), BL-83 (b, c as wants)
---
**Goal:** when two or more characters share a room, the scene is composed from each person's own personality, goals, stances and
mind. The result reaches the storyteller as one coherent section and drives what NPCs choose to do.

**Read first:** `documentation/backlog/BL-85-character-social-mind.md` (section 4 Scene and the worked kitchen example; section 6
owner decisions), `turn._build_view` (today's ten scattered directive sources), `stakes.py`, `signals.py`, `agenda.next_beat`,
`design/SOCIAL_ENGINE.md` O27 (candidate-order determinism, shared cooldowns).

**Build**
- `Scene(people, place, time)` builds dynamics from the present people's parts. Registry of kinds: rivalry, crush, triangle,
  secret_held, dramatic_irony, exposure_risk, resentment, suspicion, goal_clash, temperament_clash (MBTI/dial interplay),
  debt, alliance. Each kind: a detector over the person objects, a `tension` score, a wording template.
- Ranking with variety (damp recently shown dynamics; paraphrase duplicates share a cooldown), at most two per turn, stable
  and deterministic. Unanswered direct questions still come first.
- Rendering replaces the scattered directives with one section: each present person's card (MBTI line, active goal, stances
  toward people **in this room**), an `inner_state` of what they hide and what they think others know (subtext, never stated
  as fact), and one line naming the scene's tension. Fixed line budget; speakers first.
- `Person.wants(scene)`: ranked admissible actions (compete, needle, confide, withhold, probe, test, gossip_about, invite,
  confess, stage_talk, watch) using weighted considerations; the winner is the turn's beat. Replaces `next_beat` and `stakes.py`.
  A want never creates consent or overrides refusals, cooldowns or closed tracks.

**Tests first:** the kitchen example from BL-85 section 5 yields a triangle and a dramatic irony with nothing authored for it;
removing the witness removes the irony; rename every character and the dynamics are the same; deterministic across candidate order.

**This changes what players see: arena gate** (the arena can use OpenAI: check its providers and ask before enabling `ARENA_LLM_ENABLED`; Gemini + Jev season runs are free), plus an offline sim over
several seeds measuring how often each dynamic appears and how varied they are.

**Done when:** suite green; `SOCIAL_ENGINE.md` documents the scene layer as built; BL-85 P4, BL-84's group-energy/third-party items
and BL-83's `stage_talk`/`watch` wants are removed or narrowed in the same commit (executing them over several steps is P-15).
