# Backlog

> **One file, open work only.** Every deferred bug, follow-up, tech-debt row or owner action lives here as one `### BL-<n>` entry. When an item is fixed, **delete its entry in the fixing commit** (`Closes BL-<n>`); git history is the record. Do not keep "done" notes. New items take the next unused number (last used: **BL-48**; BL-26, BL-42 and the closed ones are gone, never reuse a number). Conventions: `/add-and-remove-from-backlog`. Read this file at session start alongside `AI_DOC_INDEX_CATALOGUE.md`.
>
> The master engineering design for the social engine is [design/SOCIAL_ENGINE.md](design/SOCIAL_ENGINE.md) (its §11a lists what is built). Owner rules for trackers are in [user_corrections.md](user_corrections.md).

## Contents
- **Terrace / social engine gameplay:** BL-33, 34, 35, 37, 43, 45, 46, 47, 25, 22
- **Correctness and architecture trackers:** BL-38, 40, 30, 31, 29
- **IU / mystery:** BL-36, 41
- **Tech debt and bugs:** BL-18, 27, 28, 32, 44, 48
- **Arena / eval / owner actions:** BL-19, 20, 23, 15, 14, 05
- **Mobile, content, engine gaps:** BL-13, 12, 11, 06, 08, 24, 04

---

## Terrace / social engine gameplay

### BL-33 — Terrace: the relationship goal and its ending are not proven end to end
- **Open:** the goal shows on the card and chat banner, and early confessions or "leave together" asks are refused with no false win (hosted, 2026-09-29). Never seen on hosted beta: the accepted path (mutual relationship, both leave, panel ending) and the female-player path. Missing pieces: natural-language decision coverage, explicit refusal and coercion cases, reload and long-skip scenarios. Rejection and leaving alone must stay valid endings; no regex win detector, no silent time limit.
- **Next:** a hosted 20-turn campaign for each player gender that earns the win (seeded campaigns already prove it offline). Depends on BL-34 and BL-35.
- **Touches:** `six_strangers_story.json`, `engine/world_model/romance.py`, `prompt_engine.py`, tests.

### BL-34 — Same-gender housemates do not visibly compete
- **Open:** a rival only states interest when asked directly ("Yeah, a bit", hosted 2026-09-29, two rosters checked). No counter-invitation, competing plan or visible rival state in about three story days. The engine fires a rival invitation only after the rival has shown interest and is co-present (`intentions.py`, `offscreen.py`).
- **Next:** independent per-rival aims that overlap the player's chosen partner, respecting schedules, knowledge and the partner's preferences; state events, not just dialogue; observable traces without exposing private thoughts. Measure across rosters (both player genders, no interested rival, mutual interest, rejection, cast rotation).
- **Touches:** `world_model/offscreen.py`, `threads.py`, `intentions.py`, relationship graph, prompt projection, tests.

### BL-35 — Plans and knowledge follow-through
- **Open:** a verbal acceptance of a later meeting ("coffee tomorrow at 10") still leaves the place empty at that time; the player is only accompanied when they invite at that moment (`companions.py`). Missing: scheduled arrival at a promised time and place, typed witnessed NPC actions, per-participant attendance, travel validation, privacy movement when a nearby resident can hear, full same-turn invitation extraction. Lapsed promise-derived plans now expire silently by design (owner rule: never register a kept promise as broken), so "missed plans affect trust" is deliberately not built.
- **Touches:** `world_model/commitments.py`, `agreements.py`, `turn.py`, extractor, prompt projection.

### BL-37 — Reply pacing, repetition and player agency
- **Open:** decorative atmosphere repeats across turns; stock phrases are reused across characters (see BL-47); narration still assigns the player feelings not stated (see BL-29); a later housemate can still ask a name the player already gave (hosted `fe54691`). Direct answers to addressed questions are handled (each addressee's first reply closes the question), truthfulness of an answer is not checked.
- **Next:** sustained-play evidence for the direct-answer and repetition gates; semantic check that answers are grounded.
- **Touches:** `prompt_builder.py`, `dialogue.py`, Terrace voice data.

### BL-43 — Name and nickname matching should be Jev's judgment under the 99% rule
- **Open:** string rules decide "same person or thing": `world_model/speakers.py` `addressed_ids`/`_name_terms`, `commitments.py` `_words`/`DUPLICATE_OVERLAP` in `record_commitment`, `memory.py` mention matching. Nicknames ("Ri-chan", "Uchi") and transliterations defeat them.
- **Next:** one bounded Jev question per ambiguous match through `npc_decision.build_resolver` (criteria as a **map**, see BL-18), uncertainty resolving toward "same" where a false match only forgets, a labeled dev set plus an untouched held-out set (pattern: `scripts/eval/promise_judge_eval.py`, cases in `tests/eval_cases/`), integration test never run on deploy, string rule deleted if the miss rate stays above the gate. Start with `addressed_ids` and the duplicate-promise check.

### BL-45 — Promise judge misses about 1% of kept promises
- **Open:** `world_model/promise_judge.py` registers a kept promise when either of two Jev questions says done. Measured 0.6-1.2% missed (gate 2%: `pytest -m integration tests/backend/integration/test_promise_judge_accuracy.py -s`), 0 wrongly kept. Remaining misses are first-person-plural completions Jev reads as pending: "We finish the whole basket together and fold everything" (case `s4-done4`, choice `pending` at 0.95), "We walk out together and I point out the pool" (`s1-done4`, flips around the 0.30 line), and an ambiguous "How's the braid?" (`h2-done5`).
- **Next, in order:** (1) a third differently framed question, keep either-says-done, confirm 0 wrongly kept; (2) reword the state text so a joint completed action reads as done; (3) write 60+ new "we ... together" and narration-only cases to a fresh third file first (the current holdout is no longer clean because the design was chosen after seeing it) and do not tune against it. At 171 cases one miss still has a 95% interval of 0.1-3.2%.
- **Touches:** `promise_judge.py` (`decision_for`, `done_decision_for`, `view_text`, `DONE_AT`), `tests/eval_cases/`, `scripts/eval/promise_judge_eval.py`.

### BL-46 — A refused "leave this house together" ask walks the player outdoors
- **Open:** hosted beta 2026-09-29 turn 12: Minori declined in dialogue and the banner stayed unchanged, but the narration moved the scene to the street for several turns ("glancing down the street", later "as you walk back to the house"). The ask reads as a movement to the extractor/heuristic (`prompt_engine.py` `_match_world_destination`, `_resolved_movement_destination`, `MOVE` intent), and `companions.py` `INVITE` also matches "let's leave", so the target travelled along. The chat response has no location field, so this was inferred from narration.
- **Next:** failing-first test through `/api/chat` with a scripted `SocialActUpdate("ask_leave_together", target)` asserting `location_id` and the target's place unchanged after a `not_yet`/`reject`; skip destination extraction on turns carrying a typed social act; drop `leave` from `INVITE`; expose `location` in the chat response for browser checks.

### BL-47 — Arrival introductions are replayed and refusal lines are reused
- **Open:** hosted beta 2026-09-29: Yuriko and Hikaru said their arrival lines a second time, word for word, when Paul greeted them (turn 9). After the first confession Minori answered many unrelated turns with "I want to take my time getting to know everyone, no big plans for now" (breakfast, moving rooms); Hikaru reused a line Minori had just said. Mechanism unverified (an arrival beat re-offered as a reply; a refusal directive or memory re-injected each turn).
- **Next:** mark an introduction delivered per character and test a greeting after arrival through `begin_turn`; find what keeps the confession outcome in front of the storyteller (`view.must_address`, relationship-decision memories in `romance.py`/`social_acts.py`) and pass it only on the turn of the ask or when raised again. Measure by counting repeated sentences in a 25-turn replay.

### BL-25 — Six Strangers prompt slips
- **Open:** (b) the murder-mystery "CANON CORRECTION" block is injected into the slice-of-life prompt for every story regardless of mode (`prompt_builder.py`); (c) pronoun and self-reference slips ("Yuki ... her" though Yuki Adachi is a man): whereabouts rows carry pronouns but Cast IDs and the speaker list do not; (d) head-count slips ("just us five" with six residents including the player), no regression suite.
- **Next:** gate the canon-correction layer on story mode; add pronouns to Cast IDs; a seeded-roster head-count regression.

### BL-22 — Six Strangers replies read as generic next to prod
- **Open:** a 40-pair arena pilot favoured prod for Six Strangers (beta 2 wins, prod 9) and the remaining explanation is that beta replies are about 30% shorter (the intentional BL-12 pacing cap) while the judge has a length bias (BL-23), so "worse" cannot be separated from "shorter". Residual: the model occasionally puts `**"bold quotes"**` inside a narration segment, which the frontend shows literally (`clean_spoken_text` only cleans dialogue).
- **Next:** length-matched arena evidence after BL-23; apply the wrapper cleanup to quoted speech inside narration.
- **Touches:** `engine/dialogue.py`, `prompt_builder.py`.

## Correctness and architecture trackers

### BL-38 — Social-engine correctness and atomic transactions (tracker)
- **Open:** durable turn/reply atomicity is only partly done. Built: request receipts in the same transaction as the state compare-and-swap (replay of the latest 200 requests, 409 on a reused id with different text, new-game receipts). Not done: the JSONL transcript (`ConversationRepo.append_turns`) and the fact-extraction outbox enqueue happen after the commit, so a crash between loses transcript or extraction work (never state or reply); early-return command paths write no receipt; scoped testimony/beliefs, single-writer relationships, old-save migration.
- **Next:** implement as part of the master design ([design/SOCIAL_ENGINE.md](design/SOCIAL_ENGINE.md) sections 3-6, 8, 10), not as a second architecture. Keep one social-state writer, at most two LLM calls, no hidden-state leakage, no fabricated consent.
- **Touches:** `prompt_engine.py`, `world_model/{turn,model,character,epistemics,agreements,projection}.py`, `character_graph.py`, session persistence.

### BL-40 — Make Bond the persisted owner of feelings
- **Open:** `Bond.feelings` is the graph's `RelationshipEdge.state`, `CharacterGraph` is still what `_serialize_state` saves, and every change goes through `CharacterGraph.update_edge`: one writer, one stored copy, owner still the graph. Storage-only, no player-facing effect.
- **Next:** move directional-feeling serialization into the character aggregate and make the graph forward to `Cast`/`Heart`, removing the separate serialization in the same commit; only after the old-save migration drill (isolated old saves with pending agreements, edges, standings; round-trip, crash/retry, rollback routing). Never dual-write.
- **Touches:** `character_graph.py`, `world_model/heart.py`, `person.py`, `prompt_engine.py` (`_serialize_state`, `_try_load_session_from_db`).

### BL-30 — Narration and the game clock still disagree in general
- **Open:** fixed (do not re-open): ISO start dates, explicit first-person durations and same-day waits, compound go-then-wait travel. Still open: generic waits, interrupted skips, other temporal claims in prose, multi-action ordering, attendance, and a full hosted chronology run. The IU authored death chronology (Jan 14-15) versus "died the prior week" and the 22 January start should be re-checked in a hosted run.
- **Touches:** `prompt_engine.py`, `state.py`, time formatting, turn extraction, `world_model/`, IU story JSON.

### BL-31 — Named NPC dialogue can be "Unknown voice" with empty presence (IU)
- **Open:** IU turns 9-12 on `67d9c4d`: narration introduced receptionist Jisoo and manager Yoo Min-ho in the EDAM lobby, every dialogue segment had `speaker_id: null` ("Unknown voice") and `people_present` was empty. Terrace speaker attribution is fine in current play; the IU mismatch and less explicit speaker mixing were never re-verified hosted.
- **Next:** an IU regression (reception to manager arrival) checking names, ids and presence across turns; an explicit policy for incidental named NPCs. Never populate presence by trusting model-generated names.
- **Touches:** `dialogue.py`, `world_model/speakers.py`, scene/presence in `prompt_engine.py`, IU locations.

### BL-29 — Narration restates the player's action and invents their feelings
- **Open:** about 20% of turns open by restating the player's typed action in second person; hosted recurrence 2026-09-29 ("Inviting her to join you in the Living Room. As you lead the way ..."). The bounded lexical echo trimmer misses paraphrases and gerund forms; invented feelings ("making your stomach grumble", "your eyes scanning its surface") bypass the filter. Any prompt change needs its own arena gate and must not trim narration that adds new information.
- **Next:** prompt rule plus a normalized first-to-second-person backstop beside `drop_player_echo`; the two verbatim examples as unit cases; an end-to-end case.
- **Touches:** `prompt_builder.py`, `dialogue.py` (`ground_social_scene`), `prompt_engine.py`.

## IU / mystery

### BL-36 — IU needs sourced evidence and unresolved contradictions
- **Open:** testimony, observation and corroboration merge. A partial post-generation repair rejects "the player told X" claims unless that NPC actually heard it, and reinspection no longer counts as a fresh discovery. Still unresolved: invented testimony provenance (paraphrase and reported speech), a player-visible evidence journal with source, speaker, time, confidence and conflict status, independent confirmation, third-person self-reference of the present player. A suspect's shifting answer must remain possible, not be "corrected" into honesty.
- **Touches:** `world_model/evidence.py`, `events.py`, `memory.py`, IU leads, journal route, tests. Needs BL-30/31.

### BL-41 — IU leads unlock records and interviews that do not exist
- **Open:** `1_iu_murder_mystery` `leads[].unlocks` names `manager_interview`, `sojin_schedule`, `aster_meeting`, `han_pressure_call`, `driver_log` with no entity, record or interview behind them (only `closet_scuff` and `cctv_side_entrance` are executable); `tests/backend/app/engine/test_leads_content.py::KNOWN_UNAUTHORED` pins the list.
- **Next:** owner authors each record (holder, access, what it truthfully shows); engine gets a generic `RecordSource` capability and a persistent `InvestigationTask` requested through the existing extraction call; missing records resolve honestly as unavailable; remove each id from `KNOWN_UNAUTHORED` as authored. The engine must never invent footage or logs.

## Tech debt and bugs

### BL-18 — Jev `noul` criteria are sent as a list; Jev rejects them (HTTP 422)
- **Open:** confirmed again 2026-09-29: a `noul` Decision with list criteria comes back from the resolver as `http_error`; the same decision with a map (`{"carried_out": "..."}`) returned a probability. `engine/extractors/decision_registry.py` (lines 182, 326, 386) and `dynamic_context.py` build noul decisions with lists and `llm/providers/jev.py` `_build_criteria` passes them through, so those abilities never get a real Jev answer on beta and the failures feed the circuit breaker.
- **Next:** convert list criteria for `noul` to a map in one place (`_build_criteria`, e.g. `{"true": c[0], "false": "not: " + c[0]}`), add a request-shape test, re-verify live that the knowledge, speaker and relationship-history batches answer.

### BL-27 — Memory and knowledge mechanisms: small problems
Fix one row at a time; delete a row when fixed; delete the entry when empty. Rows 2, 4, 10, 11, 12 and 15 change what the model sees (need the hosted arena gate); 3, 5, 6, 7, 8 are refactors touching the save format (keep old saves loading). No house or event log.
1. Static index (`retrieve.py` to `RETRIEVED_MEMORY`): chunks carry no `known_by`; one bundle per story (main character only).
2. Canonical facts (`prompt_builder.py` "others" group, ~L441-492): the focal NPC's prompt includes "Known by others — the focal character does not know this", a leak; visibility matching uses exact text.
3. `canonical_truth`: a `List[str]` duplicate of the canonical facts, used only in truth mode; derive it.
4. `BeliefState`: only the main character's beliefs are written and read; unbounded; the `[:10]` slice cuts claims.
5. `epistemic_log`: duplicates beliefs; only a playback scenario reads it; not persisted.
6. `observation_log`: dead; only `belief_seeds` write it, nothing reads it, yet it is persisted.
7. `transient_entries`: `id`/`scope`/`meta` ignored; only the debug panel reads them.
8. Room presence stored as marker strings in `transient_entries` and parsed back; needs a typed field.
9. `SceneKnowledge` (`state.scene_knowledge_entries`): an 8-item queue overwritten three times per turn.
10. `SessionChunkStore`: unbounded, no speaker or visibility tag (player claims become facts), lossy persistence, DB copy never read back.
11. Jev selection (`dynamic_context.py`): `_eligible` is a no-op (no `not_known_by`); on an exception up to 200 candidates reach the prompt unselected.
12. Conversation log: only the last 6 messages are sent (`MEMORY_TURNS`); nothing summarizes older turns (design work).
13. Graph edges: `edge.narrative` is never written during play; `disposition` is persisted but never read; only the main character's outgoing edges reach the prompt.
14. `recent_behavior_log`: part of its output is never read (see 13).
15. `Character.tells`: loaded from the story, never put into the prompt (render it or remove the field; Terrace uses `world_model/deception.py` instead).
- **Touches:** `state.py`, `prompt_builder.py`, `character_graph.py`, `prompt_engine.py`, `knowledge/runtime/{retrieve,dynamic_context,session_chunk_store}.py`.

### BL-28 — A storyteller timeout crashes the turn with HTTP 500
- **Open:** `_chat_handler_impl` (`prompt_engine.py`, the `client.post(f"{STORY_MASTER_BASE_URL}/chat/completions", ...)` inside `httpx.AsyncClient(timeout=30.0)`, through `post_with_retry`) does not catch `httpx.ReadTimeout` or other `httpx.TransportError`; only non-2xx responses return `_PUBLIC_UPSTREAM_ERROR`. The repeat-regeneration call (`storyteller_repeat_regenerated`) has the same exposure.
- **Next:** on `TransportError` log `chat_upstream_error` with `req_id` and return `{"error": _PUBLIC_UPSTREAM_ERROR}` with no state mutation (idempotent retry); keep the first draft if only the regeneration fails. Test: a fake `AsyncClient.post` raising `ReadTimeout` gives HTTP 200 with an `error` field and an unchanged session log.

### BL-32 — Hosted simulator stays "Connecting" after an initialization TypeError
- **Open:** `frontend/debug.html` `init` reads `data.stories.length` (lines ~1244 and ~1281) without checking the response status or shape; with an unauthorized or failed response the console shows `TypeError ... reading 'length'` and models stay "Loading". Also: manual `sendManual` drops returned debug payloads and `exportLog` exports the conversation only. BL-04 (operator token) is the likely cause.
- **Next:** validate status and payload before use; show an actionable authorization or unavailable error with retry; never weaken operator auth. Cover success, unauthorized and failure.

### BL-44 — Resuming a session the server no longer has leaves a blank chat
- **Open:** `frontend/index.html` `resumeGameFromSession` fetches `GET /api/user/sessions/<id>/history?limit=20`; a 404 (guest progress is deleted after 24 hours, or a local record from a failed launch) leaves "Resuming game as ..." with no messages and no error.
- **Next:** on 404 tell the player the saved game is gone, drop the local record, offer a new game; add a `tests/frontend/` check for the 404 branch and a Playwright check.

### BL-48 — Small doc/code leftovers
- `CharacterIndexBundle.chunks` is still `List[dict]`; backward-compatibility aliases from the character-model refactor are still present (see `engine/state.py`, `knowledge/`); the `INTEGRATION_TEST_PLAYBACK` browser UI was removed and only the scenario/runner/API layer remains, so its docs describe less than exists.

## Arena / eval / owner actions

### BL-19 — Arena Phase 2: server receipts, controlled init, snapshots, response forks
- **Open:** the arena is observational (public `/api/chat` plus the `[D]` box). Not built: per-turn server receipts (applied events, pre/post state hashes, component versions), seeded initialization, snapshot export/restore, the identical-state response-fork track. Checks needing them (`cast_capacity`, `rng_stream_parity`, `state_transition_legality`, `snapshot_round_trip`) report "not measured". Belongs with the `SessionFactory`/`SnapshotCodec`/`TurnService` restructure ([design/ROADMAP_NOT_BUILT.md](design/ROADMAP_NOT_BUILT.md) Phase 2); prod needs them deployed for controlled hosted parity (an explicit release decision).
- **Touches:** `api/prompt_engine.py`, `api/eval_capabilities.py`, `.claude/skills/promote-to-prod/arena/`.

### BL-20 — Arena judge needs human calibration (owner action)
- **Open:** rubric weights, the episode margin (0.55) and the critical-probe threshold (0.5) are proposals; agreement with human judgment is unmeasured, so every report says "uncalibrated: advisory only". Needs about 200 human-labeled pairs (two labelers on ambiguous cases, adjudicated).
- **Next:** label from real arena artifacts (`arena/calibration.py` `HUMAN_LABEL_FIELDS`, JSONL), add an agreement report, freeze weights and thresholds, bump `calibration_version`.

### BL-23 — Arena judge (Jev) prefers longer replies
- **Open:** the `shorten` control lost to the longer original in 3 of 3 resolved cases despite instructions; reports carry a per-game "longer side won" table.
- **Next, in order:** length-matched evidence (clip both arms to the shorter side per turn, disclosed in the packet); a length covariate in aggregation; human labels (BL-20). Then re-run the Six Strangers comparison (BL-22).
- **Touches:** `arena/evidence.py`, `aggregate.py`, `calibration.py`.

### BL-15 — Workload harness needs the full matrix run
- **Open:** `scripts/bench/turn_workload_harness.py` only ran one story at concurrency 1/3 with 2 sessions. Missing: both stories, cold/warm start, short/long conversations, movement, time skip, queue exhaustion, provider errors, concurrency 10/50 (real paid-call bursts needing a deliberate window), and `cached_tokens` in its own summary.

### BL-14 — GitHub webhook secret is recoverable from git history (owner action)
- **Open:** `deployment/gitwebhook.php` once held a literal HMAC secret (history: `2caee48`, `57c1a9a`, `612d104`, `0fa402e`, `0578a87`); the file is disabled and fails closed, but history still has the value.
- **Next:** delete the webhook in GitHub settings (preferred; the cPanel/PHP path has no live listener since Railway serves both hosts) or rotate the secret and set `GITWEBHOOK_SECRET`. History rewrite was rejected (it breaks the parallel-agent workflow).

### BL-05 — Rotate any API key that went through the old Docker build-arg path (owner action)
- **Open:** before commit `1cf4c9d` the Dockerfile persisted `OPENAI_API_KEY` from a build ARG into image `ENV`. If such an image was ever built with a real key, rotate it in the provider dashboard and the deployment secret.

## Mobile, content, engine gaps

### BL-13 — Full iOS/mobile UI overhaul not actioned
- **Open:** the 2026-09-19 plan (keyboard-safe chat shell, typing-animation rework, map/locations sheet redesign, touch targets, composer text size) was deferred; many findings are likely stale (the portrait-404 finding did not reproduce). Shipped since: wrapped home header, safe-area standalone shell, larger map close and pinch zoom, 288px portraits, a distinct beta install manifest; the user confirmed a Beta Home Screen install works on an iPhone 14. On beta at 390px the `StoriesChat` logo was partly covered by the `Play as Guest` pill (2026-09-24, re-check).
- **Next:** re-run the audit fresh before any work, then treat the survivors as one multi-commit initiative through ship-and-verify.
- **Touches:** `frontend/index.html`.

### BL-12 — Short-message pacing does not fully meet its own cap
- **Open:** replies to "hi"/"ok" fell from about 142-178 to about 120-126 tokens but still tend to two paragraphs against a stated 3-4 sentence cap; more prompt wording has diminishing returns.
- **Next:** a non-prompt lever, e.g. a lower `MAX_TOKENS` for detected-short messages in `prompt_engine.py`.

### BL-11 — NPC-to-NPC relationship edges are not authored (content)
- **Open:** `six_strangers_story.json` authors only `player->X` edges (`character_graph.get_edge("makoto", "mizuki")` is `None`), so `SocialShiftSignal` has nothing to attach an NPC-to-NPC disposition to (the safe no-op is locked by `test_social_shift_disposition_no_edge_is_safe_noop`).
- **Next:** author NPC-NPC `relationships.edges` for the pairs that matter; no engine change needed.

### BL-06 — NPC-initiated and NPC-to-NPC drift is not driven by the extractor
- **Open:** the turn extractor only accepts player-to-NPC relationship updates. Appraisal and off-screen resolution now drive NPC-side change for Terrace (`world_model/appraisal.py`, `offscreen.py`), but the extractor schema itself and the older social_sim stories (`6_common_room`) are unchanged.
- **Next:** decide whether the extractor should also propose NPC-side deltas or whether the world model fully replaces that path, then apply the same way player-facing deltas are applied.

### BL-08 — No quest, trigger or resource engine
- **Open:** per-character routines, sleep, off-screen life and commitments exist (`engine/world_model/`, declared in story JSON). Quests, flag-gated triggers and resource tracking do not ([design/ROADMAP_NOT_BUILT.md](design/ROADMAP_NOT_BUILT.md) game design systems and sidequests).

### BL-24 — NPC moves that only appear in narration are not tracked
- **Open:** routines move residents by authored blocks and `state.character_locations` mirrors the world index (`turn.py` `mirror_locations`), with residents in the scene protected from vanishing. Missing: an extractor field for narration-driven NPC moves (`npc_movements` has no hits), and per-NPC last-seen place and time so "where is Yuriko?" answers from what each character knows. No live check with an NPC leaving the room has been run.

### BL-04 — `frontend/debug.html` does not send the operator token
- **Open:** debug, playback and authoring routes require `X-Operator-Token`; the hosted debug UI never sends it, so it 401s with `DEBUG_TOOLS_ENABLED=1`.
- **Next:** an operator-token input, stored locally, sent as `X-Operator-Token` (REST) and `operator_token` (WebSocket). Likely the cause of BL-32.
