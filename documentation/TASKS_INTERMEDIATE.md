# Intermediate Tasks (Canonical)

Use this file as the single source of truth for intermediate execution tasks.

## Active

### 2026-09-29 Terrace House opening arrivals

- [ ] Integrate current beta, commit and push only Terrace task files, verify the Railway SHA and hosted opening flow.

### 2026-09-28 Engine proposal consolidation

Owner follow-up: push the consolidated proposal and record standing authorization to always push after merging/integrating into beta, including documentation-only merges. Convention aligned in AGENTS.md, Claude instructions, both backlog skill copies and the corrections log; publishing includes only committed task files, preserving unrelated attendance edits.

- [ ] Implement and verify the master release units/phases; all existing runtime acceptance gaps remain open.

### 2026-09-28 BL-39 execution (Claude, mvp_chat checkout)

Order: the four independent section-10 units first (each ships alone through ship-and-verify), then phases A–J. Each item below is one beta push with its own hosted proof.

- [ ] O09 agency: narration still invents small player feelings in real play (BL-29 note). Not yet addressed.
- [ ] O09 agency: stays in backlog (owner, 2026-09-28: not important now).
- [ ] Phase B character aggregate: `world_model/heart.py` (Bond.feelings is the graph edge state) + `world_model/person.py` (Person/Cast, scoped views, player as Person); warmth_fn reads through it. Local pytest 1332 passed.
- [ ] Phase C standing/conditions: `rules/conditions.py` (closed tri-state kinds, Viewpoint), `rules/tracks.py` (`social_tracks` JSON: TrackSpec/Tier/Requirement, loud validation), `world_model/standing.py` (StandingBook sole writer: repeat decay, daily cap, gate traversal, surplus discarded, losses while closed, explicit decay, close, idempotent effect ids, ordered journal, checkpoint + replay), `world_model/standards.py` (gates, caps, dealbreakers from the holder's view). No story declares tracks yet (phase D). Local pytest 1349 passed.
- [ ] Phase D perception/appraisal: `rules/personality.py` (temperament dials + tastes, story default + `personalities` map/character block, validated), AppraisalPolicy in `social_tracks.appraisal` (eligible any|opposite_gender), `world_model/appraisal.py` (behavior tags from the existing extraction call -> committed behavior events -> each perceiver appraises: target/witness scales, forgiveness, jealousy from the jealousy tier with test_loyalty reaction; feelings via graph once per event), private_talk events, Terrace content (closed 14-tag vocabulary, romance ladder strangers/friends/interested/dating/committed, 17 personality drafts, no dealbreakers). Found live: engine-only story keys were dropped by the runtime story projection and would have been seeded into prompt context; fixed with ENGINE_ONLY_STORY_KEYS. Local pytest 1364; real local play: Arisa ignores a looks compliment (taste 0), gains +3 for helping; witness Mizuki moves less. Content numbers are drafts pending owner review.
- [ ] Phase E claims/belief/tells: `world_model/persona.py` (immutable self-claims with audience; per-listener belief accepted/corrected/disputed), extraction rule 14 `self_claims` over story `player_fact_keys` (grounded: value words or the fact's own word stem; live play caught "I don't smoke" -> "no" being dropped), disputes raise suspicion by skepticism and record claim_dispute (never "lie"), `believed_attribute` condition (holder's belief, never truth), `world_model/deception.py` (seeded, skill/composure/pressure tells; voice-only calls hide visual cues) wired so IU suspects' authored tells can surface as behavior, requirement tells reach the scene only with hint/open disclosure. Content: Terrace player_fact_keys; IU suspect deception dials. Local pytest 1377.
- [ ] Phase F social acts: `world_model/social_acts.py` (story `social_acts` registry: confess, ask_leave_together, leave_alone, withdraw; target verdict accept/not_yet/reject from own standing tier, min standing, relationship, closed track, cooldown; directive; validate-before-display repair of contradicting yes lines; commit public accepted/declined events, relationship, departure, cooldown). Extraction rule 15 `social_act` in the existing call. romance.py commit paths shared; typed-act stories disable the regex adapters. Terrace declares the acts. Local pytest 1388; real local play: day-one confession to Yuriko -> not_yet voiced "I want to get to know you better first", declined event witnessed, no relationship. Invites/scheduling/travel stay with BL-35 (the codex checkout holds uncommitted attendance work). Target decisions use a documented local policy (standing + standards), not a model call.
- [ ] Phase G agendas/NPC life: `world_model/agenda.py` (+ `intent.py`): pursue/compete_for from each character's own standing, test_loyalty from appraisal reactions, expiry; off-screen outcome weights consult both agendas and off-screen outcomes move eligible pairs' standing via the single writer; NPC couples form only on mutual dating tier + mutual pursuit, leave after `days_together` at mutual committed tier through the existing cast replacement scheduler, `counters.couples_left`; one scene beat per turn (longest-waiting first, yields to direct questions); rival invitations from agendas for track stories. Terrace `social_tracks.couples`. Graph->Bond storage cutover deferred as BL-40 (migration risk, no player effect). Local pytest 1397; real local 2-day skip: Minori/Yuuki walk +3 each way, same-gender pairs unchanged.
- [ ] Phase H clocks/director: `rules/clocks.py` (story `clocks`: counter, warn_at, trigger_at, beats; validated; warning once, trigger once, jumping past the warning delivers only the trigger); `_build_view` delivers the director's off-camera call; Terrace declares endings explicitly (left_together, left_alone, cut_by_director loss via counter_at_least couples_left 3) and the director_patience clock (warn 2, cut 3). couples_left counts only other couples (phase G). Local pytest 1407.
- [ ] Phase I commentary: `world_model/commentary.py` (story `commentary`: panelists with own tastes, unfilmed places; dossier = committed player-involved footage kinds in filmed places, no standings/memories/private feelings/disputes; per-panelist stances; outline keeps acts + strongest behavior in time order; finale directive; scrub of internal-mechanics lines). Finale opens only on an ending known before generation (accepted leave together, leave alone, director trigger) and uses the same response call; panelists become allowed speakers and resolve in `dialogue.py` for that turn only. Terrace panel: Reina Triendl, Ryota Yamasato, Yukiko Ehara. Asides and ~300-word departure segments not built (finale only). Local pytest 1414. Live local finales found and fixed: panelists voicing housemates (panel listed with the cast), the empty-scene gate wiping the exit scene after the player walked out, and unattributed goodbyes (people being left are allowed exit voices). The model has not yet written the panel itself in 4 live finales; the footage-only fallback panel (counted in TurnView.panel_fallbacks) carried every one. Improving model compliance is phase J tuning.
- [ ] NPC decision modes (owner request 2026-09-29): `NPC_DECISION_MODE` rules/jev/compare + operator `X-NPC-Decision-Mode` override; `world_model/npc_decision.py`, `social_acts.assess()` (hard rules vs room for judgment), Jev judged through the shared resolver with a no-model fallback (two-LLM-call budget intact), `WorldModel.decision_log`, debug-box `npc_decisions`, `scripts/compare_npc_decisions.py`. Doc: reference/NPC_DECISION_MODES_2026_09_29.md. Local pytest 1464; live Jev end to end in compare and jev modes (one real Jev http_error fell back to rules with the reason logged). Pending: hosted check.

Architecture/build order for the older active list below now comes from [consolidated BL-39](design/SOCIAL_ENGINE.md). Its A–J phases and independent release units supersede competing future designs; existing P-series tests/history still supply evidence and are not marked complete by this documentation task.

### 2026-09-26 Social engine v2 implementation and hosted play

- [ ] Phase 1: canonical turn/event reducer, durable retry/revision/outbox, one clock, save/replay and scene validation; pass P1-01..08.
- [ ] Phase 2: sourced observations/testimony/gossip, character-local belief projection and privacy; pass P2-01..10.
- [ ] Phase 3: participant decisions, agreement calendar, fulfillment evidence and interruptible skips; pass P3-01..09.
- [ ] Phase 4: independent NPC intentions, rivals, directional appraisal and bounded repetition; pass P4-01..08.
- [ ] Phase 5: caused drama/repair, mutual relationship and cast-departure endings, and restrained narration; pass P5 scenarios in the design.
- [ ] Cross-phase: migration, retry, 6/30/100-character scale fixtures and a 20-turn campaign on both player-gender paths.
- [ ] Run full regression suite, integrate beta, deploy exact SHA and verify desktop Chromium, iPhone WebKit and standalone WebKit.
- [ ] After the above, personally play complete Terrace and IU hosted beta campaigns; record every turn, grade logic/engagement and repair failures before calling the work done.

Progress: the first cross-phase runtime slice has event identity and causes, observed speech, gossip roots, canonical agreements, rival invitations, conflict focus, explicit relationship/departure decisions and a terminal cast transition. The full acceptance contract remains open. Deterministic tests and local desktop Chromium, iPhone WebKit and standalone WebKit feature checks pass. Next: hosted campaigns, then repair live failures and finish the remaining architecture and scale gates.

Hosted `1045464`: completed ten-turn Terrace and ten-turn IU campaigns with full raw records; see `SOCIAL_V2_HOSTED_PLAY_2026_09_26.md (removed; see git history)`. Local corrections after that build handle explicit natural waiting and reject unidentified speech in an empty social scene. Awaiting full retest, corrective beta deploy and hosted recheck. Remaining 44-scenario architecture/quality gates stay open.

Corrective beta `c1050c9`: hosted natural-wait and empty-room replay passed; IU reinspection acknowledged no new clue; hosted desktop Chromium, iPhone WebKit and standalone WebKit interactions passed. Full social-v2 acceptance remains open (especially IU attribution, player agency, scene/commit transactions and scale campaigns).

Current corrective slice: ISO IU story clock and chronology, explicit duration/same-day waits, transport-skip prompt cleanup, leading exact-time scene repair, bounded narrator feeling/action-echo filters, and a present-housemate explicit self-introduction speaker split. Unit regressions pass; phase and final-playthrough boxes remain unchecked pending integrated/hosted proof.

Corrective beta `fe54691`: full pytest 1,245 passed/one expected failure, frontend Node 10 passed, local and hosted desktop Chromium/iPhone WebKit/standalone WebKit browser checks passed. Hosted Terrace 30-minute wait reached 7:30 pm; IU opening/inspection reached January 22 at 8:00/8:04 pm. Agency, direct-answer and mystery-source failures remain; the full campaign box is unchecked.

Current Phase 1 continuation: SQLite `game_sessions.revision` compare-and-swap, stale-cache refresh and retryable 409 are implemented with repository and API regressions. The authoritative reducer, transactionally delivered outbox and replay/fault scenarios remain open; no Phase 1 completion box is checked.

Current Phase 2 continuation: categorical NPC claims that the player said or mentioned a fact are checked against that NPC's witnessed player utterances. The observed IU false-source example has a regression and dialogue integration test. This does not complete the evidence ledger, contradiction handling, or hosted proof; keep Phase 2 and final playthrough unchecked.

2026-09-27 hosted checkpoint: played ten fresh Terrace and ten IU turns on beta `9db4b8f`; saved every request/response and graded both in `SOCIAL_V2_BETA_REPLAY_2026_09_27.md (removed; see git history)`. IU chronology and clue deduplication improved, but a new `mention`-form false source appeared. Terrace accepted a 10 am date but nobody arrived, and compound wait/movement commands misapplied. Failing-first local regressions and narrow repairs are in progress. The user-requested *final* full playthrough remains unchecked until the phase and cross-phase checklist is complete.

First corrective hosted check on `024bcef`: the destination parser fix alone did not apply travel after a time skip. A failing API regression now asserts the saved room, and the local composition fix awaits full suite, beta deployment and replay. No completion checkbox changes.

Corrective beta `4ed8361`: full suite 1,256 passed/one expected failure; local and hosted desktop Chromium, iPhone WebKit and simulated standalone WebKit flows passed. Fresh hosted gameplay confirmed Open Kitchen at 9:02 am after wait-then-go and Open Kitchen at 10:02 am after go-then-wait with a later cafe question. This closes only that command-composition slice. The accepted date did not receive attendance; all phase boxes and the final playthrough box remain unchecked.

### 2026-09-25 Terrace goal and rival mechanics

- [ ] Add regression tests and update game-design documentation, run full offline checks, integrate beta, push, and verify hosted turns. Focused tests and 1198-test suite passed; local desktop Chromium / iPhone WebKit / standalone WebKit goal-card checks passed.

### Six Strangers researched atlas and isolated Codex checkout

- [ ] Run the full suite, integrate latest beta changes, and retest as needed.
- [ ] Commit, deploy beta, and verify live artwork, data, and interactions.

- [ ] Push the final beta-ready branch after the live validation step.

## Cleanup Rules (Quick Reference)

1. Keep only open items in `Active`.
2. Delete completed checklists at task completion (no history section; git and `documentation/backlog/` are the record).
3. Deferred work becomes a `documentation/backlog/` entry, not a lingering checkbox.
