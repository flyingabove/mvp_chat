---
id: P-16
title: Generic proof (workplace story, rename test) and move the design into SOCIAL_ENGINE.md
stage: 4
size: M
depends_on: [P-12, P-13, P-14, P-15]
touches: [tests/backend/app/engine/world_model/test_generic_workplace.py, backend/app/stories/, documentation/design/SOCIAL_ENGINE.md, documentation/backlog/]
backlog: BL-85 (P6), BL-86, BL-87
---
**Goal:** prove the engine is generic and close the loop in the docs.

**Read first:** `documentation/backlog/BL-85-character-social-mind.md` (P6), `design/SOCIAL_ENGINE.md` O16 (a minimal third fixture
using data only), the "no story id, character name or gender rule in generic engine logic" rule in `SOCIAL_ENGINE.md` section 1.

**Build**
- A minimal workplace fixture (two colleagues, one secret, one promotion goal, no romance track) that produces scene dynamics
  from data alone; assert dynamics appear and consent/knowledge rules hold. Keep it a test fixture, not a shipped story.
- A rename-everything test: rename every character, place and the story id in a copy of Terrace and assert identical
  behaviour.
- Move the as-built design from BL-85, BL-86 and BL-87 into `design/SOCIAL_ENGINE.md` (one section each), delete the finished
  backlog files, and update `AI_DOC_INDEX_CATALOGUE.md`.

**Done when:** both tests pass in the unit gate; the three backlog files are deleted; `SOCIAL_ENGINE.md` describes goals, stances,
the mind, scenes, the season runner and the drama knobs as built.
