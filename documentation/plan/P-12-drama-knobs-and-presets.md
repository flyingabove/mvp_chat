---
id: P-12
title: Drama profile - tunable showrunner knobs and presets, judged by the rubric
stage: 3
size: M
depends_on: [P-06, P-11]
touches: [backend/app/engine/rules/drama.py, backend/app/engine/prompt_builder.py, backend/app/engine/world_model/turn.py, backend/app/engine/world_model/scene.py]
backlog: BL-87
---
**Goal:** the owner's tone rule for every game mode: real life, dramatized, plausible but very dramatic, achieved by tunable
nudges and never by scripted outcomes.

**Read first:** `documentation/backlog/BL-87-drama-direction-and-script-rubric.md` (design 1: the knobs and the `arc_template`
beats, with the research sources), P-05's rubric and P-06's baseline in `design/SOCIAL_ENGINE.md`.

**Build**
- `engine/rules/drama.py`: the `drama` profile (`heat`, `comedy`, `irony_bias`, `escalation`, `coincidence_budget`,
  `callback_rate`, `cliffhanger`, `threads`, `scenes_per_day`, `arc_template`, `romance_pace`), engine defaults, mode presets
  (`reality`, `kdrama`, `sitcom`, `thriller`), story overrides; validated at story load.
- Defaults reproduce today's prompts (a no-op) until a story or preset turns a knob. Each knob renders as a nudge in the
  scene prompt or as a ranking weight in the scene layer (P-11); `arc_template` beats are nudges offered to the existing
  dynamics, never forced events. Coincidences are staged only where plausible (rooms in earshot, overlapping routines).
- Switch knobs on one at a time, each measured on seeded pilot seasons by the rubric against the P-06 baseline.

**Tests first:** profile parsing and validation; defaults are byte-identical to today's prompt; each knob changes exactly its
nudge. **Spending:** the tuning sweeps run seasons on Gemini + Jev, which are free; cap each run, and ask before any OpenAI run.

**Done when:** the knob table and the measured results are in `design/SOCIAL_ENGINE.md`; BL-87's design is moved to as-built
and its remaining items rewritten.
