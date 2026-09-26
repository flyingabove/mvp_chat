# Beta manual play review — 2026-09-25 (Pacific)

I personally chose 10 Terrace turns and 12 IU turns, adapting each move to the preceding reply. No LLM player or automatic grader chose or graded these moves. Openings and debug toggles are additional setup calls, not part of the 22-turn count. These are small exploratory samples, not calibrated ratings or release gates.

| Story | Logical consistency | User engagement | My assessment |
|---|---:|---:|---|
| Terrace in the City | 5/10 | 5/10 | Pleasant and responsive, but social choices lack friction and distinctive reactions. The cooking appointment pays off in prose while the clock contradicts it. |
| Echoes of Cheongdam: IU Murder Mystery | 4/10 | 7/10 | Stronger hook and investigative progression. Dates, scene presence and speaker identity undermine confidence in the evidence. |

Overall grades weigh persistent world-state failures and the whole experience; they are not arithmetic means of the diagnostic per-turn grades below. Logic considers continuity, time/location/presence, knowledge boundaries and player agency. Engagement considers responsiveness, distinct voices, consequential choices, pacing and desire to continue. On this scale 5 is playable with substantial weaknesses; 7 is compelling with noticeable friction; 10 requires excellent consistency and sustained consequences.

## What was actually played and recorded

- Hosted endpoint: `https://beta-api.storieschat.ai/api/chat`, using the debug simulator's new-game and `[D]` protocol. All subsequent player moves were authored manually by Codex. No source canon was read to choose investigative moves; the IU canon check occurred after turn 12.
- The browser simulator at `https://storieschat.ai/beta/debug` remained on **Connecting...**, with empty story selection and models showing **Loading...**. Browser console: `TypeError: Cannot read properties of undefined (reading 'length') at init (.../beta/debug:1244:22)`. Therefore this is API-based simulator gameplay, **not 22 browser UI turns**. Main-page discovery and the simulator screenshot/console were inspected; normal game-screen interaction, mobile rendering and audio were not graded.
- Terrace: all 10 turns on commit `09633b6e580fcbf96668d7177e4013548b8b1620`, deployment `13a63fc7-eb64-4f14-a898-0131cd01e037`.
- Before a proposed Terrace turn 11, health preflight returned HTTP 502 twice. No chat move was sent or counted. The service recovered on `67d9c4d3d94b64aab269aeed480026a2a749605b`, deployment `6a69cabd-c4bf-4c85-908c-f44f53fc234d`; all 12 IU turns used that build. These are observational runs on different beta builds, not a controlled A/B comparison. Health was captured immediately before each submitted request, not a per-response server build receipt.
- Every request, setup response and complete parsed gameplay response was saved: `reply`, `segments`, `usage`, `character`, every returned `debug_box`, any `knowledge_resolution_updates`, timestamp, latency, HTTP status and health metadata. **Protected `prompt_debug`/full system prompts were not returned and are not claimed to have been captured.** Public debug fields are evidence, not a complete server-state dump.
- Local evidence bundle (intentionally outside git/runtime data): `C:/Users/Christian/.codex/visualizations/2026/09/26/01a0db51-becd-71b3-909e-45507bae9801/beta-playthrough/`. Open `playthrough.html` for readable replies and expandable full records; `all_records.json` contains all 26 calls (22 gameplay + four setup). `six_strangers_complete.md` and `iu_murder_mystery_complete.md` retain full text and debug records. The browser screenshot is in the task tool output; the bundle includes its textual observation and console error, not screenshot bytes.
- All 22 submitted gameplay calls returned HTTP 200. Terrace mean response time **7.00 seconds** (5.49–8.83); IU **5.29 seconds** (4.11–6.95). These are full HTTP round-trip times, not UI time-to-first-token or broad service benchmarks.

## Terrace: what worked and what lost me

The welcome works: Masako and Misaki greet Alex in the kitchen; Hikaru, Arman and Natsumi are in the living room. Five NPCs plus the player is the correct six-person household. Asking for food and names receives direct answers. Moving between kitchen and living room updates the public location and people-present fields correctly in this sample.

The cooking lesson is the strongest relationship beat. Misaki accepts tomorrow at seven (turn 5), and the later scene has her preparing stir-fry (turn 9). Picnic planning also produces concrete contributions: Alex's omelette sandwiches, Natsumi's snacks, Hikaru's drinks and Arman's Yoyogi Park suggestion.

However, nearly every exchange is agreeable encouragement. Natsumi's answer to an explicit invitation to disagree is another explanation of a supportive house. There is little independent initiative, competing preference, awkwardness, humor or cost. Distinct occupations appear, but the voices remain interchangeable. I felt like I was arranging activities with accommodating assistants rather than getting to know a household.

Specific failures and limits:

1. **Time is inconsistent (turn 9).** I explicitly go to bed and skip to tomorrow at 6:55 pm. The reply says "The next evening" and "You arrive at 6:55 pm". Debug stays on **2025-01-01 09:19 PM**, only eight minutes after turn 8. Turn 10 remains January 1 at 9:26 pm. A supported dedicated skip command may exist, but accepting natural-language time travel in prose while leaving the clock behind is still a contradiction. BL-30.
2. **Follow-through is incomplete.** Turn 3 drops both the proposed appointment and the question about Masako's childcare doubts when I move rooms. A multi-intent prompt can reasonably require prioritization, but an unanswered plan needs a visible pending/declined response. Turn 10 recalls stir-fry but never answers which food I admitted struggling with (rice, turn 2). This is an omitted answer, not proof the underlying memory was deleted; the attempted single-question follow-up was not sent because health failed.
3. **Player feelings are authored.** Turn 7: "making you feel more at ease"; turn 10 repeats that claim. Turn 3 adds "a sense of purpose" to my dish-carrying. These are instances of existing BL-29.
4. **Privacy and information flow are ambiguous.** In turn 5 I quietly address Misaki "just between us"; nearby Masako hears and responds. Since Masako was already there, this is not proof of impossible knowledge. It should instead clarify the lack of privacy or offer a private interaction. Likewise Hikaru's overheard omelette detail (turn 3) is plausible through adjacent rooms. Turn 10 assumes Misaki wants in on Saturday without answering whether she has heard the plan; offscreen sharing may be plausible, but it is not established.

| Turn | Player move / outcome | Logic /10 | Engagement /10 |
|---|---|---:|---:|
| 1 | Introduce Alex; names, stir-fry and kitchen help answered | 8 | 7 |
| 2 | Admit poor rice; request lesson; Masako discusses childcare | 7 | 5 |
| 3 | Propose tomorrow at seven; move rooms; meet three others; questions dropped | 6 | 6 |
| 4 | Ask Natsumi about her real day; occupations emerge | 8 | 5 |
| 5 | Confirm lesson and confide quietly; nearby Masako joins | 6 | 5 |
| 6 | Return to living room; propose inexpensive outing | 8 | 6 |
| 7 | Set Saturday eleven and food duties; Arman selects Yoyogi | 7 | 5 |
| 8 | Invite disagreement; ask house rules; more reassurance | 8 | 4 |
| 9 | Sleep and skip to tomorrow's lesson; prose succeeds, clock fails | 2 | 7 |
| 10 | Ask for food-memory recall and picnic knowledge; incomplete answers | 4 | 4 |

## IU: more compelling, but evidence needs trustworthy state

The ghost reveal is effective. IU identifies herself as the previous tenant, recalls confinement and admits what she cannot remember. Inspecting the closet yields scratches; she says they "might" be from her but cannot be sure. That distinction between observation and interpretation is exactly what a mystery needs. Questions then produce an actionable name, the manager's agency connection, a reception encounter and a suspect conversation. I would continue to see whether the calendar corroborates him.

The writing repeatedly uses heavy air, shadows, trembling voices, flickering expressions and unspoken truths. These devices initially establish atmosphere but soon feel like padding around a few lines of information. The user has to supply almost all investigative momentum. The opening response also contains literal backslash-n sequences and markdown; that is confirmed in the API text, but whether the ordinary game UI cleans it was not tested.

Specific failures and limits:

1. **The dead character's stated death is in the future relative to game time.** In turns 5–6 IU says January 15, 2025, shortly after midnight. Every debug clock in the run is January 1, 2025. This is a state/prose contradiction, even if the recalled death date matches authored story intent. After gameplay, source inspection found `world.start_datetime = 2025-01-15T09:00:00` and a January 14/15 death window; the same story also says "died the prior week", an additional authoring inconsistency. Root cause of the live January 1 clock was not established. BL-30.
2. **Waiting and next-day movement do not agree with time state.** Turn 9 accepts "next workday at 9 am" and narrates "The next morning", but debug is January 1 at **9:53 pm**. Turn 10 narrates a thirty-minute wait, while debug advances only thirteen minutes to **10:06 pm**. BL-30.
3. **Named people are not represented as named speakers or present characters.** Turns 9–12 identify receptionist Jisoo and manager Yoo Min-ho in narration. Dialogue segments use `speaker_name: "Unknown voice"`, `speaker_id: null`; public `people_present` remains `[]` in the EDAM lobby. This is a confirmed representation mismatch. It does not prove every private server object lacks those characters, nor that the receptionist must be a canonical cast member. A named incidental NPC still needs a coherent presentation identity. BL-31.
4. **The suspect's dates drift, but intentional dishonesty remains possible.** Turn 10 says his last apartment visit was "a few weeks before" his last meeting with IU; turn 11 gives January 8 and January 12/13, only four/five days apart. When challenged, he attributes it to blurry memory and promises to check calendars. This could be a useful suspect inconsistency, so I do not call it a proven canon hallucination. At turn 12 no independent calendar result has arrived. The game should preserve this as an unresolved discrepancy, not quietly overwrite it.
5. **Player agency slips recur.** Turn 9 invents "a mix of anticipation and caution". Turn 10 adds nodding, smiling, rising and taking a breath; turn 12 adds another nod. Some scene transitions reasonably imply movement, but emotions and social agreement should not be supplied for me. BL-29.

| Turn | Player move / outcome | Logic /10 | Engagement /10 |
|---|---|---:|---:|
| 1 | Turn on lamp, ask identity; ghost directly identifies previous tenant | 8 | 8 |
| 2 | Ask last personal memory; confinement account | 8 | 7 |
| 3 | Ask witnessed identity/voice; no clear memory | 7 | 6 |
| 4 | Inspect closet without disturbing it; scratch clue and uncertainty | 8 | 8 |
| 5 | Photograph; ask date/case/finder; date supplied | 4 | 7 |
| 6 | Ask year and source of time; clock recollection added | 3 | 6 |
| 7 | Ask last visitor; Yoo Min-ho named | 7 | 8 |
| 8 | Ask relationship/contact; manager at EDAM | 6 | 7 |
| 9 | Next workday reception visit; named receptionist but unknown speaker/empty presence | 2 | 7 |
| 10 | Wait thirty minutes; ask manager last visit; unclear chronology | 3 | 7 |
| 11 | Separate visit from last meeting; dates conflict with previous interval | 4 | 7 |
| 12 | Challenge interval and seek corroboration; calendar follow-up promised | 4 | 6 |

## Changes I would prioritize

1. **Make the narrated time and scene agree with committed state.** Apply validated time jumps/waits before rendering, or explicitly decline/clarify them. Make named arrivals and dialogue identities agree with scene presence. A detective game especially depends on this foundation. BL-30/31.
2. **Keep an explicit, player-readable record of promises and evidence.** Lesson: person/time/status. Picnic: invitations versus confirmed attendees and duties. Mystery: observation versus testimony versus corroboration, with sources and unresolved contradictory dates. The lesson recall is encouraging; this sample does not prove robust persistent commitments. Review existing memory work in BL-27 before adding another store.
3. **Give Terrace housemates individual wants and credible boundaries.** For example, someone might have work Saturday, prefer a different outing, or disagree about chores. Make this arise from their circumstances, not random conflict. Existing BL-22 already tracks character distinction; these observations strengthen the need.
4. **Reduce decorative repetition and leave my emotions/actions to me.** Spend more of each reply on a new reaction, clue, decision or consequence. Existing BL-29 includes the agency failure.
5. **Restore the simulator UI and handle unavailable/unauthorized data visibly.** Validate the status response before `data.stories.length`; render a useful error rather than indefinite Connecting/Loading. Verify both authorized and denied/unavailable responses. BL-32. Full prompt capture should remain operator-authorized.

The review and follow-up records are documentation only. No game behavior was fixed, no runtime deployment is claimed to have been verified for these documentation changes, and no production action was taken.
