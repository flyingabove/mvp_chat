---
id: P-07
title: Goals on the character - weighted, shifting, visible to the storyteller
stage: 2
size: M
depends_on: [P-03]
touches: [backend/app/engine/world_model/goals.py, backend/app/engine/world_model/person.py, backend/app/engine/rules/personality.py, backend/app/engine/state.py, backend/app/engine/world_model/bootstrap.py]
backlog: BL-85 (P1)
---
**Goal:** every character holds goals with weights ("love 0.8, career 0.6", or "watch the world burn"), goals can shift when
events happen, and the active goal reaches the storyteller on the character's scene card. The MBTI line already reaches
the prompt (`rules/mbti.py`, commit `b81bab0`); do not rebuild it.

**Read first:** `documentation/backlog/BL-85-character-social-mind.md` (section 1 table, section 6 owner decisions: goals
change and need not be love; mode rules such as "a mutually committed Terrace couple leaves" are data on top), the
free-text `goal` trait in `backend/app/engine/state.py` / `social_traits.py` (`EvolvingTrait`), `rules/personality.py`.

**Build**
- `Goal(id, kind, target?, weight, shifts)`; kinds are a closed, story-extensible list (love, career, status, belonging,
  keep_secret, revenge, protect, chaos). `shifts` are conditions from `rules/conditions.py` that raise or lower a weight (for
  example "competition heats up", "after a public refusal").
- `Person.goals` reads story JSON (`personalities[key].goals`) and the existing goal trait; weights change only through
  the same single-writer discipline (history kept in `EvolvingTrait`); persisted with the save and backward compatible.
- The scene card (`turn._build_view`) shows the active goal of each present character. Behaviour consequence for this
  task: goals scale the agenda priority (a career-first person pursues less); nothing else yet.
- Validation: unknown kind, weight outside 0..1, a shift naming an unknown condition fail loudly at story load.

**Tests first:** weights load and round-trip; a shift fires from the holder's own view only; the card text shows the goal;
a sparse character gets neutral behaviour. **This changes what players see: it goes through the arena gate** (the arena can use OpenAI, so
check its providers and ask before enabling `ARENA_LLM_ENABLED`; a Gemini + Jev season run is free and needs no approval); the golden record (P-03) must differ only where goals are configured.

**Done when:** suite green; design doc `SOCIAL_ENGINE.md` section "Personality model" gains the goals subsection; BL-85's P1
line is deleted.
