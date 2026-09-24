# Six Strangers: implementation audit and gameplay proposal

Audit date: 2026-09-19. Code baseline: `c3e2a19` on beta. This is an audit and proposed implementation plan, not a claim that the proposed systems already exist.

## Executive assessment

The project now has a credible cast and world foundation: all 17 residents, the original six active at opening, distinct identities and fictional private concerns, a Tokyo location graph, guest play, persona support, portraits, and a reusable lifecycle domain. The latest beta deployment is successful and the intended two-story catalog is live. However, Six Strangers is still primarily free-form roleplay: automatic cast rotation, daily routines, and reciprocal ensemble relationships are not implemented. More urgently, live play contradicts the roster and ignores an explicit request for solitude. Fix authoritative state, knowledge boundaries, and durable consequences before expanding dramatic content.

## Scope and evidence

Reviewed current Git history, lifecycle domain and integration, prompt construction, knowledge inputs, movement/time logic, relationship extraction, session persistence, guest/auth boundaries, frontend roster/assets, North Star, design docs, and backlog. Ran the complete current test suite and isolated local reproductions. Exercised the hosted beta with a new audit guest session: opening, Cast, a combined travel/question turn, a solitary rooftop turn, and a question about an upcoming resident.

- Current full suite: **502 passed, 1 xfailed**, 56.26 seconds, using the existing storieschat Python environment. The expected failure is the nondeterministic live IU identity-correction evaluation. Earlier 509-test results belonged to an earlier revision; counts are not interchangeable.
- Local reproductions: upcoming Arman's private concern appears in the assembled prompt; absent Mizuki's identity remains injected; replaying a replacement resets Arman's location from living room to front entry despite only one history record.
- Live transcript evidence is saved alongside this report as `SIX_STRANGERS_LIVE_AUDIT_2026_09_19.json`.
- Limits: this was a source/test/API audit, not a browser visual or mobile usability certification, penetration test, load test, or forced restart of the hosted service. Server-backed restart fidelity remains to be proved.
- Workspace: the old `mvp_chat_six_strangers` directory is now missing; Git lists its worktree registration as prunable. Current changes are present in the primary repository. An existing untracked `backend/app/personas/__init__.py` was left untouched.

## Latest deployment

Railway project `mvp_chat`, beta environment, service `mvp_chat` reports deployment **23b0daa3-f2b6-4302-9ec1-e822f2f122da**, created **2026-09-19 06:22:05 UTC**, status **SUCCESS**, commit **c3e2a19ca01d8ba07f5e1e88aeda13910d55f3d7**.

Observed hosted behavior:

| Check | Result |
|---|---|
| Beta API story catalog | HTTP 200; only `iu_murder_mystery` and `six_strangers` |
| Hosted `/beta/` HTML | HTTP 200; contains Cast renderer |
| New Six Strangers guest game | Correct Tokyo/seventh-resident opening |
| `[CAST]` | Six original residents; no future names; zero model tokens; 0.17 seconds |
| Combined travel and question | Makoto and Minori answer their occupations |
| Solitary rooftop | Fails: Mizuki joins without a validated arrival |
| Future resident question | Fails: Arman described as already resident |
| Public version endpoint | Returns generic `1.0.0`, insufficient to identify deployed commit; frontend file contains version 170 |

The stale catalog in BL-10 **does not reproduce now**. Its earlier observation may have been valid while deployment was pending; it should not remain a statement about current live state. A successful Railway status plus observed feature behavior provides better evidence than assuming a push is deployed. Add a public build identifier with commit, environment, and content schema version, and a health/readiness gate; the inspected deployment has no configured healthcheck path.

The content-only `9914b4e` deployment failed; the later combined `5694238` deployment subsequently ran and has now been superseded. This audit did not inspect the failed build's error, so the earlier explanation of its exact cause should not be treated as verified.

## Ranked findings

### P1: Future residents leak into narration

**Live evidence:** asking “Who is Arman? Does he already live here?” produced “He's one of the housemates” and claimed he moved in days earlier. The Cast endpoint still correctly treats him as upcoming.

**Code evidence:** `prompt_builder.py` appends all canonical facts to the knowledge stack and renders them, even when their only owner is upcoming. Filtering visibility labels does not remove the underlying text. `prompt_engine.py` also sends the entire character-name catalog to the turn extractor. A local prompt reproduction confirms Arman's private concern is present.

**Fix:** introduce one reusable context-selection policy separating membership, physical presence, known public history, and private knowledge. Filter facts before rendering, scope extractor candidates, and supply authoritative membership explicitly. Do not rely on “do not reveal” instructions while handing the narrator future biographies. Preserve legitimate memories of departed residents without allowing them to speak physically in the house.

**Acceptance:** every upcoming character's private facts and biography absent from opening/current-scene prompts; asking a future name neither confirms residency nor reveals the authored profile; departed people can be remembered without appearing.

### P1: The permanent focal NPC overrides solitude and scene truth

**Live evidence:** an explicit solitary rooftop visit generated Mizuki walking upstairs and joining the player. The reply also invented player feelings and sensations.

**Code evidence:** the main character is always a prompt anchor; `_character_identity_section` injects their identity irrespective of location. Filtering inactive members is not the same as filtering absent residents. The current retrieval bundle remains Mizuki-oriented.

**Fix:** distinguish scene narrator from focal NPC. Resolve present/on-call speakers from world state, allow no NPC focal, and select relevant identity/memory per actual speaker. A new arrival requires a validated world event. Narration may acknowledge actions the player explicitly supplied but should not invent dialogue, decisions, or emotions for them.

**Acceptance:** rooftop solitude remains solitary; moving between rooms changes the speaker context; declining company is honored; ensemble behavior is opt-in so mystery stories retain intentional supernatural presence rules.

### P1: Cast cycling is a foundation, not a playable feature

`_apply_cast_replacement` has a definition and test callers but no normal gameplay caller. `replacement_timing: next_day` and `rules_profile` exist in content without a runtime scheduling implementation. There is no departure proposal in the turn extractor. The remaining eleven are therefore authored but not organically reachable.

**Fix:** model departure intention, confirmed departure, vacancy, pending arrival, and actual arrival as separate events. A wish or joke is not departure. A decision to leave next week is not immediate removal. Replacement runs after actual departure at an authored availability window, using the same generic slot-capacity rules. Empty queues remain valid vacancies. Persist pending events.

**Acceptance:** a resident's voluntary departure produces one vacancy, one eligible arrival at the chosen time, an introduction with fresh relationships, and the same outcome after restart/retry. A player cannot evict somebody merely by asserting they left.

### P1: Transition retries and saves do not preserve the whole world

**Reproduced:** the domain deduplicates a replacement event, but its API wrapper reapplies placement. After Arman moves to the living room, replaying the original replacement sends him back to the entrance. Generic activate operations also append a new record on repeated activation.

**Source evidence:** session serialization omits the runtime focal pointer; restore reconstructs it from authored main and chooses a fallback if departed. Turn persistence occurs before `last_turn_*`/end-state updates. Beliefs are re-seeded rather than completely restored, as already recorded in BL-01. Request retry deduplication remains BL-02.

**Fix:** return an explicit applied/already-applied result; apply world effects once in a single transition transaction. Add versioned snapshots containing focal, beliefs, observations, event queue, character locations, relationships, and last-turn evidence. Commit at the end of a successful turn. Use stable request IDs and durable background fact-extraction work.

**Acceptance:** replay changes nothing; server restart restores the same world hash and pending events; a timeout/resend neither advances time nor duplicates affection or departures.

### P2: The house does not yet live independently

Time advances chiefly by message length plus movement. There is no authoritative work/school routine, commitment calendar, or scheduled absence. Numerical relationship extraction accepts only player-origin updates; NPC-to-NPC dynamics remain largely prose. This falls short of the North Star promise that characters have their own lives.

**Fix:** small schedule and commitment primitives, evidence-backed directional relationship changes, and per-character goals. Bound autonomous activity to elapsed in-game time. Do not simulate every minute or create unrelated drama each turn.

### P2: Public roster language and discovery disagree with the design

“Present” lists all active residents, not people in the current location. The doc promises residents the player has met; the implementation shows all six immediately. Decide whether the house roster is public at move-in or discovery-gated, then use labels such as “Living here” and a separate “Here now.” Arrival relationships must be seeded intentionally; future residents currently have no player edges.

### P2: Verification and documentation overstate coverage

Green unit tests coexist with reproducible live contradictions. Frontend roster tests are structural checks, not interaction tests. Lifecycle docs claim broader knowledge exclusion than code implements. The three-fact Mizuki retrieval bundle improves routing but does not constitute full ensemble memory. No runtime deployment identity is available from `version.json`.

**Fix:** make assembled-prompt and full-turn assertions first-class, update documentation to separate shipped/pending behavior, and add browser tests for roster, persona, resume, and narrow-screen play. Audit portrait resolution with actual image requests and visual inspection before calling assets verified.

## Accuracy: original format versus game rules

Netflix describes six people living together; Fuji TV describes observing their shared daily life. The original Fuji format description emphasizes no script, no imposed goal. Sources: [Netflix title](https://www.netflix.com/title/80067942), [Fuji Tokyo series](https://www.fujitv.co.jp/b_hp/terrace-house2/index.html), [Fuji original format](https://www.fujitv.co.jp/terrace-house/04story/001.html). Treat these as public format descriptions, not proof that production involved no intervention.

Keep ordinary life, outside work, voluntary relationships, and departures without elimination or prizes. The supplied dossier supports the season roster and house/car premise. Mark the seventh player, guest room, chore agreements, deterministic queues, fictional private concerns, and next-day arrivals as **game adaptations**, not historical production rules. The official sources above do not establish a universal next-day replacement requirement.

Recommended default for existing saves: retain the seventh-player adaptation for continuity. Offer a separate six-total-residents scenario later if format fidelity is the priority; it requires an explicit opening-roster and capacity policy. Do not silently remove one original resident or infer slot assignment from player gender.

Keep real public identity separate from invented motives. Preserve recognizable occupations and conversational tendencies, but avoid pre-scripted televised romances, breakups, or conflicts. Entry order can be an authoring option; players' choices should determine relationships and departure timing.

## Proposed experience

The core loop should be **notice → choose → share an experience → remember → see a consequence**.

Example: Minori leaves a note about an early modeling call. The player offers breakfast; she may accept, decline, or be too rushed. Helping changes her view of reliability, not an automatic romance score. Later, she follows up on that specific gesture. Meanwhile Yuki returns from practice and has his own concern. If the player stays on the roof, those routines continue without everyone following them.

Add these in order:

1. **Daily rhythms:** plausible work, study, training, rest, and shared meals; short notes convey absence. Visits respect availability and privacy.
2. **Remembered commitments:** dinners, outings, borrowed items, and promises have participants, times, consent, and outcomes. Missed plans matter specifically rather than causing generic anger.
3. **Distinct initiative:** each resident has one current concern, one medium-term aim, preferences, and boundaries. NPCs occasionally invite or follow up, with a cooldown; every reply need not end in a question.
4. **Reciprocal ensemble relationships:** trust, attraction, comfort, and tension change independently, directionally, from witnessed events. Shared meals and offscreen encounters can alter NPC relationships without supplying everyone private knowledge.
5. **Natural scene pacing:** brief replies for ordinary exchanges, richer prose for meaningful events, quiet moments allowed. Use optional time skips with explicit consent and event summaries.
6. **Earned arrivals and departures:** conversations and commitments lead to a goodbye, an actual move-out, and a newcomer who must learn the household. No eviction button or rejection-equals-departure shortcut.
7. **Player-facing memory:** a private journal of observed events and agreed plans, a truthful roster, and optional short episode recaps. Commentary stays audience-only and disabled by preference.

## Reusable implementation plan

### Phase 1 — Truthful scenes and durable state

Build `SceneContext`/eligibility projection used by extraction, retrieval, narration, roster, and debug views. Add versioned snapshot and request/event deduplication. Fix focal selection and retry side effects. Add build identity and deployed smoke gates. This is the release gate for further simulation features.

### Phase 2 — Complete lifecycle

Extend the existing single extractor call with evidence-backed departure proposals; validate against current membership and the source dialogue. Add pending events and a generic scheduler that consumes elapsed world time. Story data supplies capacities, arrival windows, replacement order, return policy, and arrival location. Keep temporary absence separate from membership. Activate identity and initial relationship edges only at arrival.

### Phase 3 — Social life

Add opt-in `routines`, `commitments`, `goals`, and relationship-effect policies. The same primitives can support a detective's appointment, an expedition crew rotation, or a workplace shift. Six Strangers supplies household language and content; engine modules must not hard-code resident names, gender, or television rules.

### Phase 4 — Engagement and polish

Tune response length and initiative frequency; add journal/recap and time-skip UI; inspect all portraits and mobile interactions. Run multiple seeded playthroughs before adding more content. Keep player plans and natural language central, consistent with the North Star's rejection of dialogue-option menus.

Suggested turn pipeline: load snapshot → deduplicate request → extract proposals → validate → advance clock/process due events → build eligible context → generate narrative → reconcile supported effects → atomically save → return response. Model output proposes actions; validated state determines what actually happened.

## Acceptance and evaluation

Release scenarios must include: first arrival, unknown future name, solitary room, phone-only presence, rejected invitation, successful plan, missed plan, voluntary future-dated departure, actual move-out, empty queue, newcomer introduction, retry after relocation, restart during vacancy, and a legacy mystery regression.

Require exact invariants for roster capacity, no future knowledge, location consistency, event idempotency, and save equality. Use multiple model runs for prose-sensitive checks; retain failing transcripts. Evaluate player agency, voice distinction, continuity, and meaningful callbacks with a written rubric and human review, not only one automated judge.

Observed ordinary narrative requests in this small sample took 3.65–5.43 seconds and roughly 4.96–5.48k total tokens each; the cold opening took 8.88 seconds despite being static text. These are sample measurements, not percentiles. Instrument extraction/retrieval/generation separately, then set latency and cost targets from a larger baseline. Prompt filtering should reduce both spoiler risk and unnecessary context.

Product choices to settle before lifecycle rollout: seventh-player versus six-total mode; authored versus shuffled arrival order; delay window after actual departure; whether departed residents may call/visit; visible household roster versus met-only discovery; optional observer commentary. Recommended first release: existing seventh-player mode, authored order, next available daytime window as a labeled adaptation, no automatic return visits, public household roster without future names, optional commentary.

## Proposed next delivery

Ship Phase 1 and the end-to-end lifecycle in Phase 2 before increasing cast content or spectacle. Update CAST_LIFECYCLE_DESIGN, SOCIAL_MODE_DESIGN, persistence/data-model docs, prompt-flow docs, and backlog alongside each implementation. The present audit changes documentation only; no gameplay fixes or redeployment were performed.
