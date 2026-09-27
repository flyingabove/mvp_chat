# Proposal: "Leave Together" Win Condition (Terrace in the City)

- **Status:** proposal, not built. Created 2026-09-26.
- **Closes when shipped:** [BL-33](../backlog/BL-33-terrace-relationship-goal-and-ending.md).
- **Related:** [BL-34](../backlog/BL-34-terrace-rivals-with-independent-aims.md) (rivals), [SOCIAL_ENGINE_V2_DESIGN.md](../reference/SOCIAL_ENGINE_V2_DESIGN.md), [GAME_DESIGN_SYSTEMS.md](GAME_DESIGN_SYSTEMS.md) (post-milestone loop).

## 1. Goal

The player wins Terrace in the City when they convince an opposite-gender housemate to leave the house with them. The player must see this goal before the first turn, and it must be easy to reach in natural language. It must also be fair: the partner says yes only if the player actually earned it.

Everything below is generic engine code driven by story JSON. The murder mystery gets the same goal card and ending screen for free.

## 2. What exists today (commit `1045464` and earlier)

| Piece | State | Problem |
|---|---|---|
| `goal.win_text_rule` in Terrace JSON | Written | **Never shown in the player UI.** `/api/story/{id}` returns it, but only the debug player agent reads it. The IU murder mystery has the same gap: its goal is also only implied by the card description. |
| `mode.romance_goal` prompt layer (`prompt_builder.py:1039`) | Built | Tells the storyteller the objective and the eligible partners. Fine as it is. |
| `world_model/romance.py` state machine | Built | Two steps: (1) both sides literally say *"I want to date / be with …"*, then (2) on a **later** turn both say *"I choose to leave with … as a romantic partner"*. The detection is **regex on exact first-person phrasing.** A real player who types *"Hana, come away with me"* never wins. |
| Win check (`gameplay.win_condition_detected`) | Built | Reads `world_model.romance_outcome == "mutual_departure"`. Correct: state-based, not prose-based. Keep it. |
| Ending (`prompt_engine.py:3554`) | Built | Adds the raw string `END GAME YOU WIN -- turns: N` to the reply. `index.html` has no ending screen, so the player sees a debug string in a chat bubble. The next message gets "This story has ended". |
| Solo ending | Built | Also regex (`"I choose to leave the house alone"`), with no confirmation step. |

**Summary:** the state model and win check are sound. What's broken is the player experience: the goal is invisible, winning needs magic phrases, and the ending is a debug string.

## 3. The experience we want

1. **Before playing:** the game detail modal shows a **"How to win"** line under the description. When the chat opens, a pinned **Goal card** appears above the opening narration. Its text depends on the player's gender: *"Win the heart of one of the women in the house and convince her to leave with you. The other men have their own plans."* The player can reopen it at any time from the 3-dot menu ("Goal").
2. **During play:** the player builds relationships however they like. There is no meter, no house log, and no progress UI (consistent with the no-house-log rule). Progress shows up in the prose: warmer replies, private moments, and a partner who seeks the player out.
3. **The ask:** the player asks in their own words: *"Let's get out of here together."* / *"Would you ever leave this house with me?"* / *"Aoi, I want to start a life outside with you."* The engine recognizes the ask and **decides the partner's answer from relationship state**. The storyteller then writes that answer clearly:
   - **Yes:** a real departure scene closes the story, followed by the ending screen.
   - **Not yet:** the partner explains, in character, what is missing: *"I like you… but we've never even been alone outside this house."* This is the key usability feature, because a "no" teaches the player what to do next.
   - **No:** the partner clearly declines, for example because they don't feel it or are drawn to someone else.
4. **The partner can ask first:** when the partner is ready and alone with the player, they may raise leaving together themselves. A plain "yes" from the player then wins.
5. **Ending screen:** a full-screen card shows "You left together" with the partner's name and portrait, the days spent in the house, and **New game** / **Home** buttons. Leaving alone gets its own neutral ending card.

## 4. Design

### 4.1 Goal card (generic, all stories)

Add optional story JSON fields (no change to `win_text_rule`, which stays the storyteller/grader rule):

```json
"goal": {
  "win_text_rule": "...unchanged...",
  "player_goal": "Win the heart of {{PARTNER_NOUN_ONE}} and convince {{PARTNER_PRONOUN_OBJ}} to leave the house with you.",
  "player_goal_hint": "The other {{RIVAL_NOUN_PLURAL}} in the house have their own plans."
}
```

- `backend/app/api/story.py` returns `goal.player_goal` (fallback: `win_text_rule`). The `{{…}}` tokens are resolved per player gender when the session starts, using the same substitution step as `{{PLAYER_BEDROOM}}` / `{{HOUSEMATE_MIX}}`.
- The `/chat` start response includes a `goal` object. The frontend renders it as a pinned system card (new CSS class, not an NPC bubble), and the 3-dot menu gets a "Goal" item.
- IU murder mystery: add `player_goal: "Find out who ordered the killing and make them confess."` The same card then appears there too.

### 4.2 Recognizing the ask: a typed extractor decision, not regex

Add a `leave_together_decision()` to `extractors/decision_registry.py`, registered in the **existing** pre-generation extractor batch (`turn_extractor.py`, next to `departure_check`). It adds no extra LLM call. It only registers when `romance_goal.enabled` and at least one eligible partner is present (`romance._eligible_present`).

It is a `choice` question over the current player message plus the previous reply:

| Option | Meaning |
|---|---|
| `NONE` | The message is not about leaving together. |
| `ASK:<id>` | The player seriously asks this present partner to leave the house with them. |
| `ACCEPT:<id>` | The player clearly accepts this partner's own proposal to leave together, made in the previous reply. |
| `LEAVE_ALONE` | The player states a serious intention to move out alone. |

Jokes, hypotheticals ("would you *ever*…" said teasingly), questions about other people, and narration are `NONE`. Criticality is **CRITICAL**, so on extractor failure we don't guess and treat the turn as `NONE`.

This replaces `_relationship_choice`, `_commits_to_depart`, and `record_solo_departure`'s regexes. The outcome fields on `WorldModel` (`romance_outcome`, `romance_*_choice`) stay, so saved sessions still load.

### 4.3 The engine decides the answer (fairness)

The storyteller LLM would say yes to almost anything, so it must not decide. On an `ASK`, a new pure function `romance.evaluate_departure_ask(state, partner_id)` returns `ACCEPT`, `NOT_YET(reason)`, or `REFUSE(reason)` from structured state:

| Input | Source |
|---|---|
| Partner → player `affection`, `trust` | character graph edge (already updated each turn by the extractor) |
| Partner → player `suspicion`/`fear` | same edge; high values block |
| Shared romantic moments | count of `romance_relationship` / completed date agreements with the player in `world_model` events and agreement book |
| Time in house | game days since start |
| Competing bond | partner's edge to any rival (BL-34) that is stronger than their edge to the player |

Thresholds are **story data** (`mode.romance_goal.acceptance`), for example:

```json
"acceptance": { "min_affection": 0.6, "min_trust": 0.5, "max_suspicion": 0.4,
                "min_shared_moments": 2, "min_days": 3, "ask_cooldown_hours": 12 }
```

- Every threshold met → `ACCEPT`. Close (for example one unmet item) → `NOT_YET`, with the unmet item passed to the storyteller as the in-character reason. Far → `REFUSE`.
- A `NOT_YET`/`REFUSE` answer sets a cooldown (game hours, since time only moves with player turns). An ask during the cooldown gets a short, in-character "we just talked about this". Pestering applies a small trust penalty.
- Deterministic and unit-testable. No randomness is needed: the relationship values themselves already come from play.

The old explicit "mutually choose a relationship" first step is **dropped as a separate player chore**. Mutual romance is now measured by the acceptance thresholds rather than by a magic sentence. The `romance_relationship` event is still written when an `ACCEPT` happens, so the causal chain in `world_model` events is preserved.

### 4.4 Storyteller directive

When an ask is evaluated, `prompt_builder`'s romance layer adds a one-turn directive:

- ACCEPT: *"{Partner} says yes, in their own words, in first person. Then write the two of them packing and leaving the house together as the story's closing scene. Other residents present may react. End the story there."*
- NOT_YET: *"{Partner} does not agree yet. They say so kindly and clearly and give this reason in character: {reason}. The door stays open."*
- REFUSE: *"{Partner} clearly declines. Reason: {reason}."*

On high-readiness turns where the partner is alone with the player, the layer may also allow the partner to raise leaving together themselves (this is how a later `ACCEPT:<id>` from the player happens).

### 4.5 Verification, then the ending

The storyteller might ignore the directive, and we must never declare a win that the prose contradicts. So after generation, **only on ACCEPT turns**, run a single small Jev check: *"In this reply, does {Partner} agree to leave the house with the player?"*

- Verified → set `romance_outcome = "mutual_departure"`. The existing code then removes both people from the world, records the partner in cast history, and sets `state.over = True`.
- Not verified → no win. Log it, keep the evaluation, and let the next ask re-evaluate without a cooldown.

For `ACCEPT:<id>` (the player accepting the partner's own offer), the partner's words are already in the previous reply, so the pre-generation extractor has verified them and the ending scene is written this turn.

### 4.6 Ending payload and screen

- Replace the `END GAME YOU WIN -- turns` string with a structured field on the `/chat` result:
  `"ending": {"kind": "win" | "solo", "title": "You left together", "partner": {"id", "name", "portrait"}, "days": 5, "turns": 83}`. Keep the plain-text line only in `debug.html`'s path, which already detects `END GAME YOU WIN`.
- `index.html`: after the last bubble finishes animating, show the ending overlay (adapted from `debug.html`'s existing "YOU WIN" overlay styles). Resuming a finished session shows the overlay again instead of the "This story has ended" bubble.
- Solo ending: `LEAVE_ALONE` shows a confirm sheet ("Leave the house alone? This ends your story.") before the engine commits, so a stray sentence can't end a run by accident.

## 5. Files touched

| File | Change |
|---|---|
| `backend/app/stories/7_six_strangers/six_strangers_story.json` | `goal.player_goal(_hint)`, `mode.romance_goal.acceptance` |
| `backend/app/stories/1_iu_murder_mystery/iu_murder_mystery_story.json` | `goal.player_goal` |
| `backend/app/api/story.py` | expose resolved `player_goal` |
| `backend/app/engine/extractors/decision_registry.py`, `turn_extractor.py` | `leave_together_decision`, registration, result field |
| `backend/app/engine/world_model/romance.py` | `evaluate_departure_ask`, typed-decision entry points; delete the regex adapters |
| `backend/app/engine/world_model/model.py` | `romance_last_ask_minute`, `romance_last_verdict` (serialized, default-safe) |
| `backend/app/engine/prompt_builder.py` | one-turn directive in the romance layer |
| `backend/app/api/prompt_engine.py` | wire the decision → evaluation → post-reply verification; `goal` on start; `ending` payload |
| `frontend/index.html` | "How to win" in the modal, pinned Goal card, menu item, ending overlay, solo confirm sheet |
| Docs | move built parts into a `reference/` doc; update `SOCIAL_MODE_DESIGN.md`; delete BL-33 |

## 6. Tests

- **Decision registry:** `ASK`/`ACCEPT`/`LEAVE_ALONE`/`NONE` resolution; not registered when the goal is off or no partner is present.
- **`evaluate_departure_ask`:** each threshold individually unmet → `NOT_YET` with that reason; far below → `REFUSE`; all met → `ACCEPT`; cooldown; competing rival bond; partner not present / rotated out / same gender → not askable.
- **Both player genders** (M asks F, F asks M) and a same-gender ask that is rejected as ineligible.
- **False positives:** a joking hypothetical, "let's go to the store", "Ren and Aoi should leave together", narrator text, and a player asking on the partner's behalf never end the game.
- **Verification:** directive says ACCEPT but the reply refuses → no win; reply accepts → win, both removed from the world, cast history updated.
- **Persistence:** win and solo outcomes survive save/reload, and a resumed finished session returns the `ending` payload.
- **Goal card:** gender token resolution; IU fallback to `win_text_rule`.
- **Browser (ship-and-verify 4a):** goal card and modal on desktop Chromium and iPhone WebKit; ending overlay on both.
- **Hosted beta:** one guest run per gender reaching a real win, one `NOT_YET`, and one solo ending.

## 7. Build order (each step shippable)

1. Goal card and "How to win" (both games). Small, and visible right away.
2. Ending payload and ending overlay, still driven by today's state machine.
3. Typed `leave_together` decision replacing the regexes.
4. `evaluate_departure_ask` with thresholds, NOT_YET reasons and cooldown, plus the storyteller directive.
5. Post-reply verification, the partner-initiated proposal path, and the solo confirm sheet.
6. Threshold tuning from hosted playtests (how many turns does a realistic win take?).

## 8. Decisions for the owner

1. **Does winning end the game?** NorthStar says "Solving the main mystery doesn't end the game." Recommendation: end the run with the victory screen now, and treat an epilogue or continue-after-win as a later milestone.
2. **Target length:** roughly how many in-game days (or turns) should a good player need? This sets the default thresholds (proposed: at least 3 days and 2 shared moments).
3. **Can the player lose?** For example, the chosen partner leaves with a rival off-screen. Proposal: no hard loss for now. The house refills per cast lifecycle and the player can pursue someone else (BL-34 territory).
4. **Goal card wording:** the default text in §4.1, or your own copy.
