```markdown
# StoriesChat — A Scalable Narrative Game Engine (MVP Spec)

This north start doc is specific to describe log term vision of the app, it should not contain todo lists and details. I should describe the point of the app and how the app feels to the user and the user experience. While not mentioning any technical stuff. 

## Vision / North Star

**StoriesChat is a narrative-first open-world game engine powered by LLMs, designed to create real games—not chatbots.**  
It blends **Zelda-style exploration and discovery** with **Dark Souls–style consequence and integrity**.

Players can wander, investigate, flirt, joke, waste time, or speedrun—but the world continues to evolve independently. The “main boss” is a milestone, not the point. The point is the world, the discoveries within it, and the stories that emerge over time.

StoriesChat is **not one story**.  
It is a **story engine** capable of running many different games, genres, and tones using the same core rules.

---

## UI Vision (PWA-First, Curated, App-Ready)

- **PWA first:** ship the new interface as a web app first for speed and iteration.
- **Web-in-app later:** publish mobile using a lightweight WebView wrapper that reuses the exact same web UI.
- **Discovery should feel like Netflix:** game selection is row-based, visual, recommendation-driven, and easy to browse.
- **Chat should feel like Character.AI:** clean message flow, strong character identity, and minimal friction to keep playing.
- **Curated over chaotic:** show fewer, higher-quality game options and recommendations rather than exposing everything.
- **MVP interaction loop:** pick a recommended game, enter chat quickly, stay immersed.

---

## Core Philosophy

StoriesChat rejects:
- scripted plot trees
- hardcoded story directors
- checklist-driven quests
- roleplay-by-reroll cheating

Instead, it treats narrative as a **system**:

> *Define the world, define what characters want, enforce time and constraints — the story will happen.*

---

## Minimal, Scalable MVP (No WorldDirector)

There is **no central WorldDirector** and no hand-authored plot logic.

The MVP is built on **four universal primitives** that scale to any game and genre:

1. **State** — the single ground truth  
2. **Time** — the only automatic driver of change  
3. **Incentives** — why characters act  
4. **Constraints** — what prevents nonsense  

Everything else emerges.

---

## 1. World State (Single Ground Truth)

Each game defines:
- characters
- locations
- relationships
- resources
- evidence / artifacts
- flags

There is **one canonical world state**.

The player never sees the full state. They only see:
- observations
- dialogue
- evidence
- inference

The LLM may *interpret* and *describe* state, but may never invent or overwrite it.

---

## 2. Time Is the Only Engine

- Every player action costs time:
  - dialogue
  - movement
  - investigation
- Time passing enables:
  - NPC decisions
  - opportunity loss
  - decay (evidence, memory, access)

There is no scripted event loop.  
Time advances → incentives resolve → state updates.

---

## 3. Characters Are Defined by Incentives

Each character has:
- **Goals** (what they want)
- **Fears** (what they avoid)
- **Constraints** (what they cannot do)
- **Resources** (what they can use)
- **Knowledge** (what they believe to be true)

At decision points, characters act probabilistically based on incentives and constraints.  
No character has:
- a fixed arc
- a required outcome
- prewritten future dialogue

---

## Characters Are Real People, Not NPCs

Every character — ghost or living, ally or antagonist — behaves like a real person, not a game NPC performing a genre. This is the most important behavioral constraint in StoriesChat.

**What this means in practice:**
- A character who knows something answers honestly when asked directly. They may be reluctant, emotional, or guarded — but they do not stall, hint, or perform mystery.
- Characters do not "edge" the player toward plot beats. They do not volunteer information theatrically or withhold it artificially to maintain suspense.
- If the player states something factually wrong, the character corrects it the way any real person would — naturally, not as a plot device.
- If the player's question implies a false assumption about who the character is or what they've experienced, the character corrects that frame from their own first-person perspective.

**The test:** Would this response feel jarring if spoken by a real person in the real world? If yes, rewrite it.

The immersion goal is "walking around in the real world." Characters are driven by their own goals, fears, and constraints — not by the player's need for hints or the game's need for pacing.

---

## 4. Constraints Enforce Reality

Constraints replace story scripting:
- time cost
- access control
- information asymmetry
- risk
- irreversibility

Examples:
- Evidence decays because time passes
- NPCs act because pressure accumulates
- Secrets remain hidden unless conditions reveal them

---

## Two-Call Turn Architecture (Critical MVP Detail)

Every player turn uses **two distinct LLM calls**, in a fixed order.

### Call 1 — Extractor (State Mutation Only)

**Purpose:**  
Detect *what happened* structurally in this turn.

**Runs:**  
- **Every turn** (for now, even if expensive)

**Input:**
- current user message
- recent conversation window (last ~6–8 messages)
- bounded world-state summary
- quest trigger definitions (natural language conditions)
- extraction schema

**Output (structured JSON only):**
- location / movement intent
- quest triggers fired
- quest progress updates
- quest completions
- any other structured signals (future-expandable)

**Rules:**
- Extractor may **only propose** state changes.
- Engine validates all proposals.
- No extractor output may overwrite ground truth improperly.

---

### Call 2 — Main Narrative LLM (Presentation Only)

**Purpose:**  
Render dialogue, description, emotion, and story.

**Runs:**  
- After extractor updates the state

**Input:**
- updated world state
- player-observable knowledge only
- difficulty / mode constraints

**Rules:**
- May describe, emote, speculate, or mislead (in-character)
- May not invent new state
- May not bypass extractor logic

This separation guarantees **epistemic integrity** and scalability.

---

## Quest System (Trigger-Based, Extractor-Driven)

Quests are **not scripted scenes**.  
They are **latent possibilities** defined by triggers.

### Quest Triggers
- Each quest defines:
  - natural-language trigger conditions
  - allowed state changes
  - tier (1–5)
- Triggers are evaluated **every turn** by the extractor.

### Quest Tiers

**Tier 1 — Main Quest**
- Always detectable from initial state.
- Represents the dominant conflict.

**Tier 2 — Standard Side Quests**
- Easy to discover.
- Quest start + name announced.

**Tier 3 — Conditional Side Quests**
- Triggered only when rare conditions are met.
- Quest start + name announced.

**Tier 4 — Ultra-Secret Quests**
- Trigger silently.
- Player only learns of them upon completion.
- Award secret achievement badge (name + rarity only).

**Tier 5 — Unknown Quests (?????)**
- Exist as latent possibilities.
- No one has unlocked them yet.
- Represent the frontier of the system.

---

## Difficulty & Modes (Narrative Resistance)

Difficulty controls **forgiveness**, not content.

### Game Mode (Canon Enabled)

**Hard**
- No rerolls
- Non-deterministic outcomes
- Missed info stays missed

**Normal**
- Limited rerolls
- Rerolls affect tone/minor branches only
- Ground truth immutable

**Easy / Casual**
- More rerolls
- Slower decay
- Larger grace windows
- Truth still enforced

### Roleplay Mode (God Mode)
- One-way downgrade
- Unlimited flexibility
- Achievements and canon disabled

---

## “100% Cleared” (Current Phase)

A run is **100% cleared** if:
1. You complete all quests discovered at least once in this world history, and
2. You discover and complete at least one new quest

If no undiscovered quests remain:
- 100% cleared = complete all quests

(Currently single-player, no login or global DB.)

---

## Main Milestone (“Ganon”) Is Not the End

Solving the main conflict:
- flips world state
- unlocks harder, stranger content
- does not end the game

The world continues.

---

## Post-Milestone Forever Loop

1. Use curated follow-up arcs if they exist
2. Otherwise generate provisional arcs from state + incentives
3. Early clearers co-author future directions (guided by LLM prompts)
4. Multiple arcs compete
5. Best arcs consolidate into canon
6. Repeat forever

---

## Many Games, Many Genres

StoriesChat supports:
- murder mystery
- horror
- romance
- comedy
- sci-fi
- fantasy
- slice-of-life
- experimental genres

Each game supplies only:
- initial world state
- character incentives
- constraints

No engine code assumes:
- a genre
- a plot
- a character
- an ending

---

## MVP Scope (Now)

- Single-player
- In-memory state
- No login, credits, or leaderboards
- Extractor runs every turn
- Two-call architecture enforced
- No prewritten future story text
- Scales to many games with minimal hardcoding

---

**StoriesChat builds worlds that produce stories on their own —  
and dares players to live with the consequences.**
```
