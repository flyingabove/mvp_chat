# Social v2 hosted play review — 2026-09-26

Build: beta `1045464868b83c4f8360e32fc2a24caeff29d4d8`, confirmed by `/api/health`. Two fresh guest sessions were played for ten consequential turns each, in addition to their authored openings. Every request, response field, ordered segment, latency, health stamp and timestamp is preserved in the local `social-v2-hosted-play` artifact directory next to the earlier beta playthrough. This file records the assessment; the JSON records are the complete transcript. The corrective clock/scene-guard changes described below were only local at the time of this run.

## Terrace, male player, ten turns

The player met Masako and Misaki, proposed a private curry date with Misaki, tried to meet at 7 pm the next day, queried the actual clock, apologized for lateness, asked whether she wanted romance, and respected her preference to remain friends. Misaki's explicit friendship boundary was a useful, plausible response. The ending goal was not reached in this run.

| Turn | Input/intent | Observed result |
|---|---|---|
| 1 | Ask what is cooking and who lives here | Answered, but narrator assigned the player feelings and repeated warm kitchen atmosphere. |
| 2 | Invite Misaki to cook privately tomorrow | Misaki accepted in dialogue; narration again assigned player feelings. |
| 3 | Confirm curry tomorrow at 7 pm | Misaki did not answer; Masako volunteered to join the private plan. |
| 4 | Reassert that the plan is private | Misaki confirmed 7 pm and just the two of them; Masako backed off. |
| 5 | Wait until tomorrow at 7 pm | Clock did not advance; reply remained on the prior evening. |
| 6 | Use dedicated `DAY` skip | Actual clock advanced past 7 pm, but narration asserted the date was beginning at 7 pm and invented Misaki's arrival. Four lines displayed as “Unknown voice.” |
| 7 | Ask exact current date/time | Reply said January 2, 2025 at 8:45 pm, exposing turn 6's contradiction. |
| 8 | Ask Misaki whether she was present at 7 and apologize | Unknown voice claimed she ran errands and arrived late, without a reliable speaker identity or witnessed source. |
| 9 | Ask whether this is a date or friendship | Misaki, again displayed as Unknown voice, chose friendship for now. |
| 10 | Respect friendship and cook | Unknown voice continued, and the narrator assigned the player's observations/feelings. |

Logical consistency: **3/10**. Engagement: **5/10**. A personal boundary gave the player a meaningful answer, but scheduling, speaker identity, private-plan scope and clock consistency undermined consequences. The new authoritative agreement and ending states were not visibly proven by this run because generated speech/presence did not satisfy the mechanics.

## IU mystery, female player, ten turns

The player identified IU, separated her memory from inference, inspected and photographed closet scratches, questioned the source of claims about missing objects, challenged invented provenance, and revisited the closet for new evidence.

| Turn | Input/intent | Observed result |
|---|---|---|
| 1 | Ask the unseen speaker's name | IU identified herself directly. |
| 2 | Ask what she remembers versus suspects | IU identified herself as the previous tenant and said her memory was fragmented. |
| 3 | Inspect closet without touching | Narration revealed shallow scratches. |
| 4 | Photograph scratches; ask whether IU remembers making them | No IU answer, although narration referred to “her words.” |
| 5 | Repeat as yes/no/uncertain | IU said she did not remember making the marks; this was a useful source distinction. |
| 6 | Ask what was missing and who told her | IU said phone and lyric notebook; then falsely attributed news of other missing things to the player, Mira. |
| 7 | Mira explicitly denied saying this | IU repeated the attribution. |
| 8 | Mira repeated denial and asked for evidence | IU continued to remember Mira asking, leaving invented provenance unresolved. |
| 9 | Inspect floor/hardware for new evidence | The already photographed scratches were narrated as though newly discovered. |
| 10 | Ask if anything genuinely new is present | IU repeated her earlier reaction and did not answer the question. |

Logical consistency: **4/10**. Engagement: **5/10**. Initial clue discovery and IU's uncertainty worked, but the source error and rediscovery broke investigation progress. Atmospheric passages repeatedly displaced direct answers.

## Corrections and remaining acceptance

After this run, a failing-first test reproduced the natural 7 pm wait bug. A narrow explicit first-person wait parser advanced the authoritative clock in local play, yielding January 2 at 7:00 pm. A social scene gate now suppresses unidentified speech and invented arrivals when no resident is actually present, and removes common narrator claims about the player's internal feelings. Inspection now distinguishes first discovery from reinspection in its scene contract. These corrections require a new beta SHA and hosted retest. They do not solve IU's invented source, broader natural time expressions, false time references in all prose, or the full 44-scenario social-v2 campaign. BL-30, BL-33 through BL-38 remain open.

## Corrective build replay

Beta `c1050c9ac8c6ed08eb4a2d3fd05666d7784cb620` became healthy after Railway's index rebuild. In a fresh Terrace session, “I wait until tomorrow at 7 pm in the kitchen” returned the authoritative **January 2, 2025, 7:00 pm**; with no resident co-present, the reply contained no unidentified dialogue or invented arrival. In a fresh IU session, first inspection revealed the closet scratches; second inspection answered that there was **no new evidence**, rather than staging the scratches as a discovery again. Full requests and responses are saved as `corrected_*` JSON records in the same local artifact directory.

Hosted browser checks also passed on desktop Chromium, iPhone WebKit and simulated standalone WebKit against `https://storieschat.ai/beta/`, with calls to `beta-api.storieschat.ai` and no page, console or API failures in the scripted flows. Screenshots still show narrator lines such as “You can feel the potential for connection” and repetitive atmosphere. The scene guard catches only a narrow set of player-internal assertions; agency/pacing and IU source attribution remain open. The corrective replay proves these specific fixes, not completion of the full social-v2 design.

## Clock and scene correction replay

Beta `fe54691933f2d82f4a277a87667ca0bea32bad02` was confirmed by `/api/health`. In a fresh Terrace session, explicit “I wait for 30 minutes” moved the debug clock from the authored 7 pm start to **September 2, 2015, 7:30 pm**. In a fresh IU session, the authored evening opening began on **January 22, 2025 at 8 pm**; inspecting the closet recorded **8:04 pm** and revealed the shallow scratches. The raw responses and health stamp are in the local `social-v2-followup-hosted-smoke` artifact folder. This is a focused clock/inspection replay, not a full ten-turn assessment.

Hosted desktop Chromium, iPhone WebKit, and simulated standalone WebKit flows passed with `beta-api.storieschat.ai` as the API host and no browser/API errors; screenshots are in `social-v2-followup-hosted-feature`. The screenshot review still found decorative atmosphere and a housemate asking the player's name immediately after the player said they introduced themselves. IU inspection still narrated “Your eyes scanning its surface.” Thus the new filter and clock fixes are real but the broad agency, direct-answer, provenance and engagement gates remain open. No revised overall grade is assigned from these short replays.

## Revision-check replay

Beta `bc18e492fa830d743cf647b6cc4edb7c8e699a2a` reached `/api/health` after Railway startup. A fresh Terrace turn advanced exactly 30 minutes and a second HTTP request with the identical request ID returned the identical saved response. A fresh IU opening and closet inspection also completed. Raw health, requests and responses, including `terrace_wait30_retry.json`, are in `social-v2-followup-hosted-smoke`. This proves the live idempotent retry path; simultaneous requests on separate hosted workers were tested at the repository transaction boundary, not by the short hosted smoke.

Desktop Chromium, iPhone WebKit and simulated standalone WebKit browser flows passed against the hosted page with calls to `beta-api.storieschat.ai` and no page, console, network or API errors. The screenshots in `social-v2-cas-hosted-baseline` and `social-v2-cas-hosted-feature` were inspected, including mobile chat and the bottom navigation. The dialogue still spends too many words on atmosphere and sometimes implies the player's feelings; this revision work does not address that quality gap. The full phase checklist remains open.
