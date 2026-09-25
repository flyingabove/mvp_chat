# Living world, open investigation, and conversational initiative

Date: 2026-09-24. Status: proposed design; no runtime implementation or quality gain is claimed.

## 1. Player goal and boundaries

The player's target is an open world that behaves like a place, rather than a sequence of puzzle prompts. Two players should be able to follow different credible paths and learn different things because of where they went, whom they trusted, and when they acted. The player may combine physical observation, conversation, records, travel, waiting, and social judgment. A discovered detail is not automatically important; a character's statement is not automatically true.

The game must remain playable without highlighting every clue. Fairness comes from **multiple grounded routes to each necessary inference**, stable world rules, and natural opportunities to recover from a missed lead. It does not come from mandatory hint bubbles or a checklist that identifies the culprit.

This proposal extends [JEV_DYNAMIC_CONTEXT_DESIGN.md](JEV_DYNAMIC_CONTEXT_DESIGN.md), [GAME_DESIGN_SYSTEMS.md](GAME_DESIGN_SYSTEMS.md), [SOCIAL_MODE_DESIGN.md](SOCIAL_MODE_DESIGN.md), [WORLD_ATLAS_DESIGN.md](WORLD_ATLAS_DESIGN.md), and [CAST_LIFECYCLE_DESIGN.md](CAST_LIFECYCLE_DESIGN.md). The context selector currently implements broad retrieval, Jev relevance Noul judgments, one deterministic anchor, and seeded optional power sampling behind an opt-in flag. Clue pacing, NPC routines, and the conversation policy below are **not implemented**. The current world clock advances on turns and travel; `world_calendar.py` supplies day numbers and persisted pending events for cast transitions, not a general daily routine engine.

## 2. The player's points and the mechanism for each

| Player requirement | Mechanism | Authority |
| --- | --- | --- |
| Many kinds of clues, found through different play styles | Typed evidence and claim records with observation channels, prerequisites, provenance, and independent discovery routes | Story data + engine |
| Physical observation should matter | Location and object affordances; inspection resolves authored properties and records what was actually noticed or collected | Engine |
| Conversation should reveal different information | Speaker-specific knowledge, beliefs, incentives, trust, risk, and question intent; a witness may be mistaken or evasive | Engine + bounded semantic judgments + storyteller |
| Two players can take different paths | Persistent time, location, access, NPC availability, evidence handling, relationship consequences, and optional opportunity sampling | Engine |
| Clues should be subtle without becoming arbitrary | Eligibility and direct answers are deterministic; optional surfacing is probabilistic, capped, and allowed to be absent | Engine, with Jev scoring fit |
| The world should continue around the player | Daily routine templates, commitments, travel, sleep, interruptions, and scheduled events | Engine |
| Characters feel alive and engage the player | Each present NPC has a current activity, immediate conversational aim, and initiative budget; dialogue reacts to the player's actual words | Engine packet + storyteller |
| Terrace conversations need a gentle next-turn opening | Natural conversational handoffs: a question, offer, interruption, shared activity, observable reaction, or a comfortable pause | Storyteller under a varied ending policy |
| The model must not invent facts or teleport people | A narrow authorized context packet, structured proposals, validation, and committed-state replay | Engine; Jev/LLM never own canon |

## 3. An evidence ecology, rather than a pile of clue text

Author a **case graph** of questions, claims, events, objects, people, places, and possible inferences. Each evidence record has a stable ID; kind; source and timestamp; physical or social location; visibility; owner; durability/decay; prerequisites; what the player can observe; what each speaker believes or is willing to say; and a claim or event it can support or contradict. Store `observed`, `collected`, `heard`, `verified`, and `inferred` separately. The UI may show the player's notes and provenance, never engine-only motive fields.

Clue families to support across stories:

1. **Physical traces:** damage, fibers, residue, object placement, missing items, wear, temperature, and sounds. Observation may depend on light, access, tool, and time.
2. **Documents and digital records:** receipts, schedules, messages, access logs, photographs, edits, and metadata. Access and authenticity are separate.
3. **Witness accounts:** a remembered sight, sound, time, or conversation, with source reliability and memory limits.
4. **Behavioral observations:** a pause, avoidance, habit change, or repeated visit. These are observations, not certified motives.
5. **Social-network clues:** who knows whom, who vouched for whom, and who changed an account after talking to somebody.
6. **Temporal and geographic clues:** route duration, opening hours, sleep/wake time, travel opportunity, and an alibi's feasible window.
7. **Absences and inconsistencies:** a missing item, a log gap, two accounts that disagree, or a claim incompatible with an established event.
8. **Voluntary disclosures:** confidences, admissions, promises, and explanations that may be partial or self-serving.
9. **Indirect consequences:** a cleaned room, a person arriving late, an invitation withdrawn, or a witness becoming cautious after the player shows evidence.
10. **Ordinary detail:** stable background texture that may be useful later but is not secretly treated as an omnipresent clue.

These are **types**, not ten mandatory clues per case. Author enough instances that the same inference can be approached through different modes of play. For a required inference, design at least two independent discovery routes, preferably from different families; test reachability after reasonable delays and missed opportunities. Some leads can expire, but a single missed roll must not make the central case impossible. False leads need a grounded cause: mistaken memory, a real but irrelevant trace, deliberate deception, or misinterpretation. Random generation may choose among authored eligible surfaces; it may not create evidence to justify a predetermined twist.

Example using the beta playthrough: a closet scratch and fabric scrap become two physical records. A player might compare fabric to a known garment, ask a cleaner about a damaged jacket, inspect a dated photo, or pursue the access log instead. The engine records which route was actually used. It does not label the scrap “the murder clue” in the journal.

One case inference could be “somebody entered the apartment after the reported departure.” Player A notices the scratch, finds the relevant access-log gap, and tests the route timing. Player B never enters the closet; they earn a cleaner's testimony, see a timestamped photo, and catch a witness revising their account. Both can form the inference without receiving the same staged hint. The inference is still a player conclusion until the world supplies stronger proof. The engine can record that these paths support the same question without telling the storyteller to announce it.

## 4. World time, routines, and autonomous behavior

Use the existing absolute world minute and atlas travel graph. Time advances when the player acts, travels, waits, or explicitly skips. Resolve elapsed intervals in chronological order, including sleep boundaries and events crossed during a long skip. This keeps a coherent clock without requiring the server to simulate every idle real-world minute.

Each NPC receives an authored **routine envelope**, not a rigid scene script:

- Normal activity blocks by weekday/time (work, commuting, meals, social time, sleep), with candidate locations and travel constraints.
- Exceptions: appointments, promises, emergencies, temporary access changes, and player-caused commitments.
- Private preferences and constraints: willingness to talk, need for solitude, fatigue, trust, risk, and what they know.
- A current plan plus next planned transition, persisted for replay.

At a schedule boundary, code constructs only feasible actions: continue, travel to a reachable place, keep a commitment, contact someone, rest, sleep, or choose `NONE`. Jev can score a **small feasible set** for contextual fit where semantics matter; code applies a seeded draw and revalidates capacity, travel time, access, and commitments. This is an optional scene-boundary operation, not one Jev call per NPC per chat turn. If Jev is unavailable, a deterministic policy uses authored priorities. The storyteller describes the resulting state; it does not decide where every NPC happens to be.

NPC-to-NPC interactions also need durable effects, but only at relevant event boundaries: two housemates who share a meal can exchange a permitted fact, form a plan, quarrel, or do nothing. The engine records who actually heard what. A later rumor spreads through a valid contact, not through an omniscient cast-wide memory update. When the player enters mid-conversation, the scene may reveal only its audible surface; the private cause remains private.

Sleep is a real availability state. Sleeping NPCs do not casually answer or appear elsewhere. The player may wake someone if the location and relationship permit, with an appropriate response and fatigue consequence. A late message or phone call can be unanswered, delayed, or answered by a willing awake character. Nobody should be declared “out” solely because the prose needs an empty room. On arrival, use the current location index and schedule result to tell the player who is actually there.

Avoid a metronomic world: routine envelopes allow plausible variance in departure time and activity choice, seeded per session/day and bounded by commitments. The player can learn patterns, yet an NPC can be delayed for a real reason. Persist the sampled plan and resulting events so save/resume, retry, and investigation of an alibi agree.

## 5. One turn, with clear ownership of truth

1. **Interpret the player action.** The existing structured extractor proposes movement and several state signals. Extend its typed output to capture interaction targets, speech acts, inspection, collection, and the time period named in a question. A bounded Jev decision may help classify ambiguity (question about the past versus tonight; invitation versus commitment; inspection versus collection). Preserve an ambiguous request when it cannot be resolved.
2. **Validate and advance.** Code checks the world graph, access, time cost, inventory/evidence handling, and who can hear the action. The clock and queued events advance; routines update locations and availability.
3. **Resolve earned discoveries.** Direct inspection of a valid object or a permitted direct question retrieves the corresponding authorized record deterministically. Jev may find a semantic match among records, but a low score cannot hide an earned answer.
4. **Select optional context.** Reuse broad source-balanced recall and Jev relevance judgments, then filter by visibility, cast, time, provenance, repetition, and token budget. The seeded sampler may offer a natural clue or callback, including no offer. Keep this separate from required answers.
5. **Build the storyteller packet.** Supply what the speaker can know and say, the player's observable scene, validated action outcomes, and a small set of optional opportunities. Include source IDs in internal metadata.
6. **Generate the scene.** The OpenAI storyteller produces attributed speech and narration, with a permitted conversational handoff. Its output is presentation, not an authority to mutate canon.
7. **Validate and commit.** Check speaker presence, fact IDs, allowed disclosure, travel, time, player agency, and formatting. Reject unsupported state changes; repair or regenerate with a smaller packet if necessary. Persist only accepted discoveries and statements, including their exact source and turn.

The current code already has a structured pre-render extractor, a prompt builder, and a post-response pipeline. This design adds typed evidence, routine resolution, a selected packet contract, and validation at those seams. It does not require an unbounded “director” model making every world decision.

## 6. What goes into context, and what must be said

Keep a stable instruction prefix where possible, followed by a compact **turn packet** with distinct lanes:

| Lane | Contents | Rule |
| --- | --- | --- |
| Scene authority | Absolute time, player location, route result, present/awake speakers, accessible objects, immediate event outcomes | Code-owned; always included |
| Direct response | The specific question/action, matched authorized records, source/provenance, permitted disclosure, explicit uncertainty | Must be answered or honestly declined |
| Speaker lens | This speaker's knowledge, beliefs, current activity, goals, relationship history, and reasons to withhold | Scoped to actual speaker; never pasted as player truth |
| Continuity | Recent accepted turns, established commitments, physical evidence handling, contradictions still open | Required only when relevant to this turn |
| Optional texture | At most a few eligible memories, observations, callbacks, or NPC initiatives with usage labels | May influence wording without being mentioned |
| Prohibitions | Specific absent people, unknown facts, impossible actions, already removed objects, and player actions not taken | Enforced in code as far as possible |

**MUST mention** means a narrow player-facing obligation, not “recite every selected clue.” It applies to: the direct result of the player's validated action; an answer the addressed speaker can provide; a material consequence of time or travel that just occurred; a hard boundary that blocks the action; or an event the player directly perceives and cannot reasonably miss. A sleeping witness's non-answer, a locked office, or a lost appointment belongs here. An eligible background clue, a relationship callback, and a character's unspoken motive do not.

Give each optional item a usage label (`background_constraint`, `optional_observation`, `optional_callback`, or `required_answer`), disclosure ceiling, valid channel, source ID, and repetition cooldown. The storyteller may use zero optional cues. A high Jev relevance score means “useful for this response,” not “true,” “important to the mystery,” or “must appear.” Never inject the full hidden culprit explanation into the writer and hope a prompt will suppress it.

## 7. Probability with fairness and replay

There are three different probabilities:

1. **World variance:** whether an NPC takes one of several feasible routine actions or whether a contingent event occurs. Never randomize fixed culprit/canon facts or previously committed events.
2. **Jev judgment:** whether a candidate is relevant, a conversational move is natural, or two claims address the same issue. Jev's Noul is a yes-probability for its specific rubric, not a general confidence in truth.
3. **Presentation selection:** whether an eligible optional cue is surfaced now. Code applies quality floors, cooldowns, caps, and the existing power-sampling exponent; a scene may remain quiet.

Record independent RNG streams for routines, optional clues, and conversation initiative. Seed by session, turn or scene, and policy version; persist the chosen result and scores. On retry, reuse the chosen packet. Calibrate thresholds against human-rated scenes and actual player paths, rather than treating a model probability as a tuned game rate. The current [dynamic-context design](JEV_DYNAMIC_CONTEXT_DESIGN.md) already proposes a gradually rising, capped chance for unsolicited investigative cues and a deterministic direct-answer lane; use that policy instead of a second competing clue formula.

## 8. Terrace: a conversation beat that invites another turn

For a social scene, the packet should state: who is present, what each person is doing now, the player's exact speech act, recent shared history, current relationship stance, a near-term commitment or schedule boundary, and one or two feasible activities. Do not preload everyone’s private thoughts. The storyteller's beat should:

1. Respond to the player's actual words or action first.
2. Let a character pursue a small current aim (finish dinner, ask for help, avoid a topic, invite a walk, apologize).
3. Allow another present person to react only when they plausibly heard or saw it.
4. End on an **available human opening** when one naturally exists.

An opening can be a sincere question, an offer, a disagreement, an unfinished action, someone entering or leaving, a detail the player can inspect, or a comfortable silence. The engine tracks recent ending forms and downweights repetition. There is no required question every turn and no generic “What do you do next?” line. If the player asks for privacy or ends a conversation, respect it. A character can ask an actual question whose answer affects their next action, then remember the answer. Initiative is bounded: one principal new bid per beat unless the player triggered a group exchange; no forced romance, confession, or cliffhanger.

Example: the player says they came home late and missed dinner. A housemate who promised to save food may point to a covered plate and ask, “Want me to heat it, or do you need a minute?” If no promise exists, no plate should materialize to create a warm moment. A tired housemate could simply say goodnight and go to bed. Both endings give the player a real social situation to respond to.

## 9. Preventing hallucination and accidental spoilers

- **Schema is transport, not truth.** Use strict structured outputs for proposals and attributed dialogue segments where the chosen OpenAI model supports them, but validate IDs, transitions, and claims in code. Schema adherence does not establish factual correctness.
- **Separate records by epistemic status.** Canon, observed physical fact, attributed testimony, character belief, and player inference have different fields and display rules. A witness can lie; the engine records the lie as their statement without changing canon.
- **Project only allowed surfaces.** The storyteller gets “red fibers on a hinge” if observed, never the engine's hidden “this links suspect X to the murder” field. Journal and recap use the same player-visible projection.
- **Keep closed rosters and presence authoritative.** The current prompt already guards active cast and whereabouts; the schedule resolver must update that state before the scene is generated.
- **Validate material claims.** Deterministic checks reject unknown location/object/person IDs, impossible co-presence, unsupported collection, and disclosure outside permission. A targeted semantic check can inspect high-risk implicit spoilers or contradictions; it cannot guarantee perfect prose. One bounded repair/retry is preferable to silently accepting an invented clue.
- **Tie authoring and testing together.** Every essential inference needs reachable routes; every misleading lead needs provenance; every generated statement that changes play needs a source or validated event. Retest after model or prompt changes.

## 10. Build order and proof

1. **Evidence state and player projection:** typed records, discovery states, source IDs, journal filtering, and save/resume. Fix the observed beta problem where the Journal reveals private suspect goals yet omits the player's fabric scrap and scratch.
2. **Routine resolver:** schedule envelopes, sleep, travel, commitments, event order, and persisted location plans. Prove scene presence after travel and long time skips.
3. **Turn packet and direct-answer contract:** distinguish required response from optional context; ground physical inspection and questions in valid records; block unsupported evidence.
4. **Conversation initiative:** speaker aims, handoff variety, questions that affect later state, and recent-ending cooldowns; pilot in Terrace before broad rollout.
5. **Optional opportunity policy:** add clue/callback pacing and Jev semantic scoring behind the current task flag and fallback path; evaluate against the deterministic baseline.

Test with identical starting snapshots and multiple player strategies, not just a scripted “correct” path. Required checks: clue reachability through at least two paths; no private-goal journal leaks; no absent or sleeping speaker; consistent alibis across save/resume and time skips; physical evidence never invented or duplicated; direct questions answered within speaker knowledge; distinct Terrace voices; varied endings; and quiet scenes that remain satisfying. Compare full-session human judgments of agency, naturalness, surprise, and frustration. The existing arena is advisory until its human calibration and reply-length bias are addressed, so do not optimize this design solely to its current win rate.

## 11. External model contracts checked

- [TypeSafe Noul documentation](https://docs.typesafe.ai/primitives/noul): Noul answers a concrete yes/no rubric with a value from 0 to 1; criteria use true/false descriptions. Thresholding and policy remain code-owned.
- [Official OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs): strict schema adherence is available for supported models; refusals and incomplete responses still need handling. This motivates typed proposals and explicit validation, not a claim that structured text is true.

This is a design proposal. It does not assert that the schedule engine, evidence graph, dialogue handoff policy, or post-response semantic validation currently exists.

## 12. NPC behavior addendum: owner decisions (2026-09-24)

Status: design decisions; nothing below is implemented.

**Decisions**

1. **Full off-screen autonomy.** "Off-screen" means any world time the player does not witness: sleep, time skips, travel, or time spent elsewhere. During it, NPCs may start relationships, argue, make plans, and commit to leaving, driven by the world clock. The player has no control over it. Consequences persist and change later scenes.
2. **No log UI.** There is never a house log, event feed or journal of off-screen happenings. The player learns only through the story: someone mentions it, a consequence is visible ("Hikaru and Yuto aren't speaking at breakfast"), a conversation is overheard, or they never learn it. Off-screen results are engine facts with per-character knowledge (§4 "records who actually heard what"), never player-facing summaries.
3. **Generic first.** Every mechanism is engine code plus story data and works in every story. One routine resolver serves housemate schedules and suspect alibis. One off-screen resolver serves a housemate romance and suspects coordinating a story. Nothing is Terrace-specific unless it is authored data.

**Turn-based time, never real time.** The game clock advances only when the player takes a turn: each message adds its minutes, travel adds route time, and sleep or an explicit skip adds the whole span in that one turn. Closing the app freezes the world; no server process advances any session in real time, and real-world absence never produces game events. One player turn can cover hours of game time. "I go to sleep" takes about a second for the player but can advance eight in-game hours, and the NPCs may produce eight hours of change: whatever awake characters would plausibly do in that span, while sleeping characters take no part in the hours they sleep through. The amount of change scales only with game minutes elapsed.

**Off-screen resolution.** It runs only when a time interval passes without the player (§4's schedule boundaries), never on each chat turn. The steps: (1) the routine resolver moves every NPC through the interval in chronological order; (2) code lists the feasible co-presence encounters (who shared a place, awake, for long enough); (3) for each encounter, code builds a small feasible outcome set (nothing, conversation, a shared activity, conflict, an exchange of affection, a plan or commitment, or a fact passing between the two) weighted by relationship state, current aims and personal threads; (4) Jev optionally scores the set, with about one bounded call per interval and an authored-priority fallback at zero calls, and a seeded draw picks the outcome; (5) the results are committed as events, relationship-edge updates, knowledge records for the participants only, and visible traces (a changed seating pattern, a new plan, someone gone to bed early). A departure decision goes through the existing cast-lifecycle `committed_intent` path.

**Extra layers beyond §4 and §8**

- **Speaker selection (engine-owned):** 1-3 speakers per beat, chosen by who was addressed, who is present and can hear, interest in the topic, recency and one rotating initiative bid. This replaces model-chosen roll calls (BACKLOG BL-22).
- **Personal threads:** each character has 2-3 authored threads (an audition, a job decision, and in a mystery a cover story under strain) with time-based milestones. They advance whether or not the player helps, and outcomes persist.
- **Reaching out:** when apart from the player, an NPC may contact them by message or call, subject to availability and relationship. A generic channel, not a feed.
- **NPC-to-NPC relationship edges** are a prerequisite for off-screen outcomes (BACKLOG BL-11).

**Build order** (replaces §10 for social stories; evidence work from §10.1 follows for mysteries): (1) routine resolver and availability (BL-24); (2) speaker selection with conversation initiative (§8); (3) personal threads and commitment memory; (4) off-screen resolution with NPC-to-NPC edges and knowledge propagation; (5) contact channel; (6) evidence ecology (§3). Each step needs a live multi-roster check and arena comparison, and a sleep or time-skip scenario proving that consequences appear only through prose.
