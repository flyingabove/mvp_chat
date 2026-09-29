# NPC decision modes: rules, Jev, and side-by-side comparison

Status: implemented 2026-09-29 for typed social acts (`confess`, `ask_leave_together`). Owner decision: build the Jev version next to the rules, make it switchable, compare them. The default stays `rules`.

## The switch

`NPC_DECISION_MODE` (environment variable, read at request time; `backend/app/config/settings.py`):

| Mode | What decides | Gameplay effect |
|---|---|---|
| `rules` (default) | the local policy: standing tier, minimum standing, cooldown, closed track, relationship | today's behavior; Jev is never called |
| `jev` | Jev picks accept / not yet / reject from the target's own first-person view | Jev's answer applies, bounded as below |
| `compare` | the rules decide and apply; Jev is asked too | unchanged gameplay; both answers are logged |

Per request, an operator can override the mode without a redeploy: send `X-NPC-Decision-Mode: jev` with a valid `X-Operator-Token` (needs `DEBUG_TOOLS_ENABLED` and `OPERATOR_TOKEN`). A player's header is ignored. An unknown value falls back to `rules`.

`jev` and `compare` also need Jev on: `TYPESAFE_ENABLED=true` and a `TYPESAFE_API_KEY` (beta already reports Jev enabled). With Jev off or failing, the rules verdict applies and the reason is recorded (`flag_disabled`, `timeout`, `http_error`, `below_threshold`, `invalid_option`).

## Bounds (why Jev cannot make consent looser)

1. Hard rules stay with the rules and Jev is not even asked: cooldown after a refusal, a closed track (dealbreaker), "must be together first" for a leave-together ask, the player's own acts (leave alone, withdraw).
2. Jev can never say yes below the required tier and minimum standing. Such a yes is clamped to "not yet" and flagged `clamped`. Jev can be stricter than the rules; it cannot be looser.
3. Jev sees only the target's own view: their nature and tastes, the stage they are at (in words), how they feel, what the player told them (disputed claims read as "unsure"), and what they noticed the player do. No other character's standing, memories or private state, and no engine internals.
4. Jev's answer is a proposal to the same validate-before-display and atomic-commit path as the rules' verdict (`social_acts.validate/commit`).
5. No extra language-model call: the resolver's fallback for this task returns nothing (`npc_decision._no_language_model`), so the two-LLM-call turn budget is untouched. Jev is a bounded classification, accounted separately.

## Where the code is

- `backend/app/engine/world_model/social_acts.py`: `assess()` returns the rules' verdict plus `hard` and `can_accept`; `decide()` is its thin wrapper.
- `backend/app/engine/world_model/npc_decision.py`: modes, `merge()`, `target_view()`, `jev_decision()`, `judge()`, `DecisionRecord`.
- `backend/app/engine/world_model/turn.py`: `npc_question()` (what to ask, or nothing) and `record_social_act(mode=, judgment=)`.
- `backend/app/api/prompt_engine.py`: reads the mode, awaits the judgment, logs `npc_decision`, shows the last three records in the debug box (`npc_decisions`).
- `WorldModel.decision_log`: last 60 records, saved with the game.

## Comparing the two

1. Fixture table (same information to both): `python scripts/compare_npc_decisions.py` (Jev calls need `TYPESAFE_ENABLED=true`; `--rules-only` skips Jev; `--show-view N` prints what Jev sees for fixture N). Prints rules answer, Jev answer, confidence, P(yes), the answer `jev` mode would apply, and a summary.
2. Live play: run with `NPC_DECISION_MODE=compare`. Every confession or ask writes a `decision_log` record `{rules, jev, final, p_accept, note}` (also the `npc_decision` log line and the debug box) while the game follows the rules. Switch to `jev` to play the Jev version.

## First results (8 hand-built Terrace fixtures, 2026-09-29; not a validated dataset)

Jev orders the cases correctly and is far more cautious than the rules in absolute terms:

- Cold-in-practice confessions, thin history, a contradiction, and a pushy couple: P(yes) 0.00 to 0.09.
- Warmest confession: P(yes) 0.31, answer "not yet". Couple ready to leave: P(yes) 0.56, but choice confidence 0.35 is below the 0.5 floor, so it counts as unavailable and the rules apply.
- Rules alone say yes to 6 of 8. Jev mode says yes to 1 of 8.

Consequence: in `jev` mode as configured, winning would be very hard. Options for the owner: keep `rules` as the default (current), keep `compare` on in playtests to collect real data, or calibrate Jev (an accept threshold on P(yes), a question rewording, or a `score` question) against labeled cases. The 0.5 confidence floor (`MIN_CONFIDENCE`) and the option wording (`CRITERIA`) are the tuning points; all are hypotheses until tested on real play.

## Not covered

Only the two targeted acts. NPC couples forming and leaving off-screen (BL-39 phase G) still use the rules alone. Invitations and dates are BL-35.
