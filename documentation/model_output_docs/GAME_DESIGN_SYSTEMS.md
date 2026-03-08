# Game Design Systems

> **What this doc is for:** Technical game-design mechanics — how the world state works, how time drives change, how quests trigger, how difficulty modes differ, and how the post-game loop works. Edit this doc when adding or changing core gameplay systems, quest tiers, difficulty modes, or win conditions.

---

## Four Universal Primitives

The engine runs on four primitives that scale to any game and genre:

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

## Two-Call Turn Architecture

Every player turn uses **two distinct LLM calls**, in a fixed order.

### Call 1 — Extractor (State Mutation Only)

**Purpose:** Detect *what happened* structurally in this turn.

**Runs:** Every turn.

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
- any other structured signals

**Rules:**
- Extractor may **only propose** state changes.
- Engine validates all proposals.
- No extractor output may overwrite ground truth improperly.

### Call 2 — Main Narrative LLM (Presentation Only)

**Purpose:** Render dialogue, description, emotion, and story.

**Runs:** After extractor updates the state.

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

Quests are **not scripted scenes**. They are **latent possibilities** defined by triggers.

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

## "100% Cleared"

A run is **100% cleared** if:
1. You complete all quests discovered at least once in this world history, and
2. You discover and complete at least one new quest

If no undiscovered quests remain:
- 100% cleared = complete all quests

---

## Main Milestone ("Ganon") Is Not the End

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

## MVP Scope

- Single-player
- In-memory state
- No login, credits, or leaderboards
- Extractor runs every turn
- Two-call architecture enforced
- No prewritten future story text
- Scales to many games with minimal hardcoding
