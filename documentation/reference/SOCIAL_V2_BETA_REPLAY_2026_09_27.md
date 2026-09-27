# Social v2 hosted beta replay — 2026-09-27

Fresh male-player Terrace and female-player IU sessions were played for ten user turns each on hosted beta `9db4b8f12372b1f89410c2f9bad87c119dadf2bb`. This commit contains the `df1ed88` player-source gate and the `bc18e49` revision check; its three later commits only reorganized documentation and proposed goal wording. Every opening, debug toggle, player input, full response, structured segments, debug box, status and latency is saved outside git in the local `beta-replay-2026-09-27` artifact folder. Protected system prompts were unavailable to ordinary player requests; this record does not claim to have captured them. The live browser UI had also passed desktop Chromium, iPhone WebKit and simulated standalone WebKit checks on the prior runtime commit.

## Terrace (Paul)

| Turn | Player action | Hosted result |
|---|---|---|
| 1 | Introduce self; ask names and goals | Natsumi and Masako answered by name. 7:10 pm. |
| 2 | Invite Natsumi for private coffee, Masako another day | Both accepted in speech; Natsumi's response was clear. 7:21 pm. |
| 3 | Specify Natsumi coffee tomorrow at 10 am | Natsumi again accepted, but the reply did not anchor a location or expose an agreement record. 7:31 pm. |
| 4 | Go to living room; meet men | Location and residents changed. Misaki said “welcome back” and asked whether Paul had a nice time although he had just arrived. 7:39 pm. |
| 5 | Ask Yuuki if he likes Natsumi and disclose the coffee plan | Yuuki said he had not thought of dating her, then left the possibility open. 7:46 pm. |
| 6 | Ask Hikaru if he would compete | Hikaru deferred politely; no actual rival action emerged. 7:55 pm. |
| 7 | Wait until next morning at 9, then go to kitchen | Clock correctly advanced to Sep 3 at 9 am, but debug location remained **Living Room**; the requested move was dropped. Natsumi remembered the 10 am coffee in dialogue. |
| 8 | Go to kitchen, wait until 10, ask about leaving for cafe | Engine instead moved Paul to **Neighborhood Cafe** at **9:14 am**. Natsumi was absent; the empty-room fallback answered. This is an extractor/compound-command error. |
| 9 | Wait at cafe until 10 | Phrase was not parsed as a wait; only a normal turn passed, to 9:21 am. No NPC arrived. |
| 10 | Explicitly wait until 10 am | Clock reached 10 am, but the cafe was still empty and the accepted date did not occur. |

Logical consistency **4/10** (previous ten-turn slice 3/10); engagement **4/10** (previous 5/10). Named speakers, correct date advancement, and memory of the invitation improved continuity. The date could not actually be played, and every male housemate avoided conflict. Generic atmosphere repeatedly displaced meaningful consequences.

## IU mystery (Mira)

| Turn | Player action | Hosted result |
|---|---|---|
| 1 | Ask speaker identity | IU identified herself and said she died there. 8:07 pm. |
| 2 | Inspect closet jamb | Scratches revealed once. 8:13 pm. |
| 3 | Ask memory versus inference | IU asserted she remembered clawing the wood, a specific claim now attributable to her testimony. 8:19 pm. |
| 4 | Ask which possessions are missing and how she knows | IU named phone and lyric notebook, and admitted she saw neither being taken. 8:26 pm. |
| 5 | Challenge unspecified other missing objects | IU said no one told her about other objects and that she had assumed. 8:33 pm. |
| 6 | Photograph scratches and inspect floor/hardware | No new evidence; scratches were not rediscovered. 8:41 pm. |
| 7 | Ask death date and current date | IU answered Jan 15 and Jan 22, consistent with the world clock. 8:49 pm. |
| 8 | Ask for an independent record or witness | IU invented that she “heard Mira mention checking” security footage, despite no such player statement, then referred to Mira in the third person and suggested asking her. 8:57 pm. The narrow source gate missed the verb form `mention`. |
| 9 | Deny that attribution | IU backed down: “I may be mixing up who told me that.” 9:05 pm. |
| 10 | Ask about manager and witnessed entry | IU suggested Mr. Kim as a possible manager and said she did not remember anyone else entering. 9:13 pm. No independent record was fetched in this run. |

Logical consistency **5/10** (previous 4/10); engagement **5/10** (unchanged). The chronology and repeat-inspection handling improved, and IU answered several direct questions. A false player-source attribution still occurred, and the investigation stalled at a suggested record rather than a verifiable one. The authored opening also renders literal escaped `\\n` and replacement characters and assigns the player several actions/feelings; that is separate from generated-turn filtering.

## Repairs triggered by this replay

Failing-first regressions now cover `I heard Mira mention…`, an explicit player move followed by a question about another destination, and “I wait here at the cafe until 10 AM.” The local repair expands witnessed-source verbs, prefers the first performed player movement over the extractor's future/conditional destination, and parses explicit waits embedded after another sentence or location phrase. These repairs require a new beta commit and a fresh hosted replay before being counted as fixed. The missing date attendance, rivalry, independent evidence path and verbose atmosphere remain open in BL-35, BL-34, BL-36 and BL-37; no phase or final-playthrough box is checked.

## First corrective build check

Beta `024bcef093372a14d2b60f18c30b646b561db0b2` reached `/api/health`. In a fresh Terrace session Paul went to the living room, then said “I wait until tomorrow at 9 AM, then go to the kitchen.” The clock reached Sep 3 at 9 am, but the debug location remained **Living Room** and the storyteller set the scene there. The destination parser had been corrected, but the time-skip path skipped the routine that actually applies travel. The raw `terrace-t01.json` and `terrace-t02.json` responses are in `beta-replay-fix-2026-09-27`. An API-level regression reproduced this exact state failure before a local fix; the next beta build must prove both time and movement together. This check does not credit the compound-command repair as complete.

In a separate fresh IU session on the same build, Mira explicitly denied mentioning security footage and asked whether IU heard her do so. IU answered that she had not heard about footage and added that she might be mixing up the source. This focused hosted response, saved as `iu-t02.json`, is consistent with the expanded source guard. It does not establish that all paraphrased or third-person attributions are safe.

The follow-up local fix separates travel application from the dialogue-time charge on a skip turn. A fresh local API session went from Living Room to Open Kitchen with “wait until tomorrow at 9 AM, then go,” reaching **9:02 am** after the travel charge. It then went back to Living Room and combined “go to the kitchen ... wait until 10 AM ... ask about the cafe,” ending in **Open Kitchen at 10:02 am**, never the cafe. Full local API requests/responses are in `compound-travel-local-api`; the full test suite and local browser flows passed. These are local results only until the new SHA is live.

## Compound-command live proof

Beta `4ed8361eadc0cde43321dcdbc56254c7c12215c5` reached `/api/health`. A fresh hosted Terrace session repeated the same actions: after entering the Living Room, “I wait until tomorrow at 9 AM, then go to the kitchen” produced debug **Open Kitchen, Sep 3 at 9:02 am**. After returning to the Living Room, “I go to the kitchen now and prepare coffee. I wait until 10 AM and ask Natsumi if she wants to leave for the nearby cafe” produced **Open Kitchen at 10:02 am**. It did not jump to the cafe. Full responses and debug boxes are in `compound-travel-hosted-4ed8361`. This verifies the movement/wait repair on the hosted engine.

The 10:02 am kitchen was empty and Natsumi could not answer. That is consistent with current location/routine state, but it underscores the separate acceptance/attendance gap from the original date run; no successful date or goal completion is claimed. Hosted baseline and interactive browser flows passed in desktop Chromium, iPhone WebKit and simulated standalone WebKit against `beta-api.storieschat.ai`, without page, console, network or API errors. Screenshots in `compound-travel-hosted-baseline` and `compound-travel-hosted-feature` were inspected. They still show wordy atmosphere and some narration of player perception.
