# Order of work and stage gates

> **What this doc is for:** the order in which engine work is built and why, with each stage's exit criteria. The tasks
> themselves (ids, dependencies, files) are the `P-*.md` files beside this one; `python scripts/work.py status` shows the
> live board. Edit this doc when the order or a gate changes, never to track progress (finished tasks are deleted).

**Rule of the order:** build the measuring tools first, then change behaviour one layer at a time, each layer standing
on the one before. The product vision is in [../backlog/BL-85-character-social-mind.md](../backlog/BL-85-character-social-mind.md),
[BL-86](../backlog/BL-86-headless-season-simulation.md) and [BL-87](../backlog/BL-87-drama-direction-knobs.md);
this plan is how they get built.

## Stage 0: groundwork
A green suite, the model providers decided, and a recording of today's NPC behaviour.
- **Exit:** unit suite passes on a machine with a populated `.env.test`; Ollama is off by default; a golden record of
  seeded Terrace decisions exists to diff every later refactor against.

## Stage 1: the measuring tools
A headless season runner on a fake writer, the Jev script rubric, and a baseline season on today's prompts.
- **Exit:** a season runs end to end offline; the rubric exists with a labelled set; a baseline score for today's
  engine is recorded (so every later stage can show it improved the drama).

## Stage 2: the character object
Goals, then stances, then the mind (first- and second-order knowledge with fog of war).
- **Exit:** the golden record still matches after stances (apart from intended, tested changes); no-telepathy tests
  pass; "where is X" is answered from the asker's own mind.

## Stage 3: drama emerges
NPC-to-NPC extraction, scene dynamics and wants, the drama knobs, the season camera and the admin watch mode.
- **Exit:** a headless Terrace season produces scenes the rubric scores at or above the baseline, with always six
  residents and no consent or knowledge violations; an admin can watch a season and read any character's mind.

## Stage 4: smarter characters and the proof
Strategies and delayed answers, background multi-step plans, and the generic (non-Terrace) proof.
- **Exit:** a minimal workplace story with no romance track runs the same engine from data alone; a rename-everything
  test passes; the design moves into `design/SOCIAL_ENGINE.md` as built and the backlog items close.

## Why this order
- **Measure first:** without a baseline, "more dramatic" is an opinion.
- **Stances before mind, mind before scenes:** scenes are composed from stances and minds; building scenes first would
  mean building them twice.
- **NPC extraction before full seasons:** otherwise an NPC-only scene is prose with no consequences.
- **Off the path:** BL-40 (Bond owns feelings), BL-38's remaining atomicity work and BL-33's hosted win runs block
  nothing here; do them when a task touches that storage, or on spare time.
