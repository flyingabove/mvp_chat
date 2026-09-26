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
