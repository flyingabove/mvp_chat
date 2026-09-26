# Jev extractor redesign — full ability mapping and test plan

September 22, 2026. Design doc for replacing `TurnExtractor`'s single generative
call with Jev (TypeSafe AI System One) bounded-decision calls.

**Status: design only.** No code in this document is implemented. It supersedes
the preliminary (and partly wrong — see §1) classification given in chat on the
same date, and refines the Jev section of
`ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md`.

**Credential:** `TYPESAFE_API_KEY` is stored and live-verified (commit
`68646ae`). Every Jev result quoted in this document is a **real response from
`jev-1.13.0`** via `POST https://api.typesafe.ai/v1/systemone`, not a
projection. Raw evidence is inline per ability in §7.

---

## 1. Correction to the earlier classification

An earlier pass classified 5 of 12 extractor abilities as "**No** — Jev cannot do
this," on the grounds that Jev returns one typed scalar per question and
therefore "cannot return a list."

**The premise was right; the conclusion was wrong.** Jev genuinely cannot emit a
list. But every "list" this extractor produces is a list over a **candidate set
the engine already knows before the call**:

| Extractor list | Candidate set already known from |
| --- | --- |
| `previous_reply_speakers` | `allowed_character_keys` (the active cast) |
| `knowledge_updates` | the ≤12 `previous_turn_candidate_chunks` we ourselves supply |
| `relationship_history_updates` | character pairs drawn from the active cast |
| `relationship_state_updates` | NPCs present in the scene |
| `behavior_tags` | ordered pairs of actors present in the scene |

When the candidate set is known, a list is not a generation problem — it is
**N named boolean/choice questions**, and the API accepts `questions` as a map
of arbitrarily many entries against **one shared `state`**, billed as **one
flat request**. Confirmed against the API reference and by measurement: an
8-question request cost 906 input tokens total, one call.

So the correct question per ability is not "is this a list?" but "**is the
candidate set knowable, and is the per-item judgment bounded?**" On that test,
**12 of 12 abilities move their judgment to Jev.** Exactly one field
(`social_shift_signal.new_value`) genuinely requires generated prose, and it is
rare and already gated. One field (`destination_text`) is dead weight and should
be deleted.

---

## 2. Verified Jev capabilities

Three question types, all confirmed working against real dialogue states:

| Type | Returns | Verified behaviour |
| --- | --- | --- |
| `choice` | one option id + `confidence` + full `probabilities` map | Picked `terrace` from 6 locations at 1.0; picked `distrust` from 8 attitudes at 1.0 |
| `score` | ordinal position + `legend` mapping levels to descriptions + `probabilities` | Returned `1.95` on a 0–2 scale with an explicit `legend` — the legend makes level→delta mapping auditable in code |
| `noul` | probability 0.0–1.0 (no `confidence` field) | 8-way fan-out over speakers/chunks/relationship facts, all correct |

Two capability facts that matter for this design:

1. **`confidence` and `probabilities` come free.** The extractor's existing
   `confidence` float field and the per-chunk `confidence` become native
   response data — we stop asking a model to self-report a number it was
   guessing at.
2. **Many questions, one request, one bill.** The API's `questions` is
   `map<string, Question>`; usage is reported once for the whole request.
   Adding questions costs only their own tokens, not a re-tokenized state.

### Documented weaknesses, and how this design respects each

Jev's own jaggedness docs (`docs.typesafe.ai/model-jaggedness/jev-1.13`) list
limits that directly shape the design. These are not caveats to note and ignore
— each one produces a hard design rule:

| Documented weakness | Design rule it forces |
| --- | --- |
| "does not count reliably" | Never ask Jev *how many*. Counting stays in code (it already is — `_ripe_behavior_pairs` counts tags with `Counter`). |
| "struggles with mathematical logic", cannot judge near-values | Never ask Jev for a **delta number**. Ask for an ordinal *level*; code maps level→delta. See ability 9. |
| "reads dates as text, not ordered quantities" | No date/time questions. World-clock logic is already deterministic code. |
| "answers the question you wrote, not the one you meant" | Every `criteria` description must state its boundary cases **explicitly**. Verified necessary: the sarcasm test only passed because the criteria literally said "sarcastic or ironic statements that actually REFUSE the movement must be NONE". |
| "accuracy falls as the state grows with content unrelated to the decision" | **Split into a few focused calls, not one mega-call**, and prefilter candidate sets (see ability 2 — send reachable locations, not all 102). Accuracy and cost point the same direction here. |
| "not trained to generate text" | Only one field needs prose; it goes to a generative model (ability 12). |
| thresholds don't transfer between question types | Tune a separate threshold per question, per model version, on labeled data. Still blocked — see §9. |

---

## 3. The design rules in short

1. **A list becomes N questions over a known candidate set**, in one request.
2. **Jev judges; code computes.** Any number, count, clamp, or invariant stays
   in Python. Jev only ever returns a category, a level, or a probability.
3. **Code enforces every invariant regardless of Jev's answer.** Jev choosing a
   location does not make travel legal; Jev saying DECISION does not by itself
   remove a resident. All existing validation in `_parse_json` and the apply
   pipeline is retained, unchanged, and remains the authority.
4. **Prefilter the state to what the decision needs.** Fewer irrelevant tokens
   is both cheaper and (per the docs) more accurate.
5. **Confidence gates the ambiguous questions only.** Most answers came back at
   1.0; the genuinely ambiguous one (`shift_certainty`) came back at 0.73. That
   difference is the signal — threshold the ambiguous ones, don't threshold
   everything uniformly.
6. **Fallback is internal and silent.** On timeout, low confidence, or an
   invalid answer, fall through to the existing generative extractor for that
   judgment. Never surface model uncertainty to the player.

---

## 4. Full ability chart — all 12

`TurnExtraction` has 12 fields. Verdicts below are backed by the live evidence
in §7.

| # | Ability | Current shape | Jev design | Verdict |
| --- | --- | --- | --- | --- |
| 1 | `movement_intent` | `MOVE` / `NONE` | 1 × `choice` | **Jev** |
| 2 | `destination_id` | pick from up to 120 locations | 1 × `choice` over **reachable-only** prefiltered set + `none_of_these` | **Jev** |
| 3 | `confidence` | float the model self-reports | **deleted as a field** — use the native `confidence` / `probabilities` | **Jev (free)** |
| 4 | `destination_text` | raw text span | **deleted.** `location_extractor.py:24` says "for logs only"; no game logic reads it | **Delete, not Jev** |
| 5 | `previous_reply_location_id` | pick from locations | 1 × `choice` | **Jev** |
| 6 | `previous_reply_speakers` | list of character keys | N × `noul`, one per active cast member | **Jev** |
| 7 | `knowledge_updates` | list of `{chunk_id, knows, confidence, reason}` | N × `noul`, one per supplied candidate chunk; `confidence` native; `reason` → code template | **Jev** |
| 8 | `relationship_history_updates` | list of `{pair, 3 booleans}` | 1 × `noul` **gate**, then 3 × `noul` per scene-present pair only if the gate fires | **Jev** |
| 9 | `relationship_state_updates` | list of 5 numeric deltas + reason | 1 × `choice` (which attitude) + 1 × `score` (how strong) per NPC in scene; **code maps level→delta** | **Jev (judgment) + code (arithmetic)** |
| 10 | `departure_signal` | `NONE`/`WISH`/`DECISION` + character + reason | N × `choice`, one per active resident, each scoped to "that resident's own words only" | **Jev** |
| 11 | `behavior_tags` | list of free-text tags per pair | N × `choice` over a **story-authored tag vocabulary** | **Jev — and it fixes a latent bug, see §5** |
| 12 | `social_shift_signal` | certainty + scope + subject + target + `new_value` + reason | 4 × `choice` for all judgment; `new_value` from **one tiny generative call, only when SHIFT** | **Jev (judgment) + 1 rare generative call** |

Nothing in this table is "cannot be done with Jev" on capability grounds. The
two non-Jev entries are: a **dead field** (#4, delete it) and **one string of
player-visible prose** (#12's `new_value`).

---

## 5. Ability 11 deserves its own note — the vocabulary change fixes a bug

`behavior_tags.tag` is currently deliberate free text, documented as
genre-agnostic by design ("a mystery story's tags read 'evasive'/'defensive', an
ensemble drama's read 'warm'/'aggressive', same field, no schema change").
Moving to a fixed vocabulary looks like flattening the sim to fit the tool —
which the engineering plan explicitly warns against.

**But the current consumer already requires a closed vocabulary and does not get
one.** `_ripe_behavior_pairs` (`prompt_engine.py:1304`) decides whether a
behavior pattern is worth a shift judgment like this:

```python
recent_majority  = Counter(recent).most_common(1)[0][0]
earlier_majority = Counter(earlier).most_common(1)[0][0]
if recent_majority != earlier_majority:
    ripe[pair_key] = list(tags)
```

That is **exact string equality**, and with free-text tags it produces
**false positives** — verified live against the real function on 2026-09-22:

| Tag window (semantically) | `_ripe_behavior_pairs` says | Correct answer |
| --- | --- | --- |
| `warm, warm, warm, dismissive, dismissive, dismissive` (real swing) | ripe ✅ | ripe |
| `warm, warm, warm, warmly, warmly, warmly` (**no change**, synonym drift) | **ripe ❌** | not ripe |
| `warm, friendly, warm, affectionate, warmly, friendly` (**no change**, all warm) | **ripe ❌** | not ripe |
| `a, b, c, d, e, f` (all distinct, no pattern at all) | **ripe ❌** | not ripe |

The mechanism is `Counter(...).most_common(1)` on all-singleton counts: when no
tag repeats, `most_common` returns an arbitrary first-encountered entry from each
half, and two arbitrary picks from two disjoint halves essentially always differ
— so the swing check fires. Any window of mostly-distinct free-text tags reads as
a genuine behavioural swing.

This is live today, because the tags *are* free text emitted by an LLM ("1-3
words") across different turns, which is precisely where synonym drift comes
from. Two consequences: an expensive shift judgment gets spent on windows with no
real change, and — worse — that judgment is then handed a noisy window and asked
whether a character's goal has shifted, risking a fabricated change written into
player-visible journal state.

Note this is the **opposite** of the failure I first assumed (missed swings). A
closed vocabulary fixes it in the right direction: repeated tags actually form
majorities, so `most_common` compares real modes instead of arbitrary singletons.

So the design rule is: **the vocabulary is authored per story in the story JSON,
not hardcoded in the engine.** Genre-agnosticism is preserved where it belongs
(content), the engine stays generic, Jev gets a `choice` it can answer reliably,
and `Counter`-based majority comparison becomes correct for the first time. This
is a fix, not a concession.

Authoring cost is real and should be acknowledged: each story needs a tag
vocabulary (≈8–12 tags) added to its JSON, plus a migration decision for
existing saved `recent_behavior_log` entries holding free-text tags (recommend:
map unknown legacy tags to the nearest vocabulary entry once on load, or clear
the log — it is a rolling window of ≤8 entries per pair, so clearing costs
little).

---

## 6. Call structure

Driven by design rule 4 (irrelevant state hurts accuracy) rather than by field
grouping. Each call carries only the state its questions actually need.

### Call A — "current player message"
**State:** current user message, scene roster, reachable locations (prefiltered),
active resident list.
**Questions:** ability 1 (intent), 2 (destination), 9 (attitude choice + strength
score per NPC in scene), 11 (player→NPC tags), 8's gate, 10 (departure choice per
active resident).
**Measured:** a 6-question version of this call cost **1,197 input tokens**.

### Call B — "previous assistant reply"
**State:** previous assistant reply, candidate knowledge chunks, roster.
**Questions:** ability 5 (previous location), 6 (speaker nouls), 7 (knowledge
nouls per chunk), 11's NPC→X tags for detected speakers.
**Measured:** an 8-question version cost **906 input tokens**.

### Call C — "ripe behavior window" *(conditional, rare)*
Fires only when `_ripe_behavior_pairs` returns non-empty — which the existing
docstring notes is "most turns... {} and zero extra prompt tokens".
**State:** the one ripe pair's tag window + that character's current goal and
disposition.
**Questions:** ability 12's certainty / scope / subject / target.
**Measured:** **552 input tokens**.

### Call D — "write the new value" *(conditional, very rare — generative)*
Fires only when Call C returns `SHIFT`. One small generative call producing the
single player-visible sentence for `new_value`. Everything else about the shift
was already decided by Jev.

**Typical turn: 2 Jev calls.** Occasionally 3. Rarely 3 + one small generative
call. This replaces **1 large generative call** today.

### Fan-out ceiling
Question count scales with scene size, so it needs a cap. For six_strangers
(6 residents, ≤5 in a scene): Call A ≈ 16 questions, Call B ≈ 25. Both
comfortable. The design should cap total questions per request (suggest 60) and
degrade by dropping the lowest-value fan-outs (behavior tags for non-speaking
actors first), never by silently truncating a candidate list that affects an
invariant.

---

## 7. Per-ability test cases

Every case below states the **state**, the **question(s)**, the **expected
answer**, and the **invariant code must enforce regardless of what Jev returns**.
Cases marked ✅ VERIFIED were run against live `jev-1.13.0` on 2026-09-22 with
the result shown. Unmarked cases are specified but not yet run.

---

### TC-01 — `movement_intent`: explicit movement ✅ VERIFIED

**State:** scene = kitchen; player message: *"Honestly Makoto, I don't believe a
word you just said. I'm going out to the terrace to cool off."*
**Question:** `choice` MOVE / NONE.
**Expected:** `MOVE`.
**Actual:** `MOVE`, confidence 1.0.
**Code invariant:** intent alone never moves the player; travel legality is still
checked against the world graph.

### TC-02 — `movement_intent`: sarcastic refusal must NOT move ✅ VERIFIED

**State:** player message: *"Oh sure, I'd LOVE to go out to the terrace with you
right now. Really. That's exactly what I want to do instead of finishing my
work."*
**Question:** `choice` MOVE / NONE, with criteria **explicitly** stating that
sarcastic refusals are NONE.
**Expected:** `NONE`.
**Actual:** `NONE`, confidence 1.0.
**Why this case exists:** the plan's gate 1 names sarcasm as required coverage.
It also proves design rule "state boundary cases explicitly" — the criteria text
had to name sarcasm for this to work, per Jev's documented literalism.

### TC-03 — `destination_id`: choose from reachable set ✅ VERIFIED

**State:** reachable = `living_room`, `terrace`, `boys_bedroom`, `kitchen`,
`gotanda_station`; same message as TC-01.
**Question:** `choice` over the 5 ids plus `none_of_these`.
**Expected:** `terrace`.
**Actual:** `terrace`, confidence 1.0, all other options 0.0.
**Code invariant:** the returned id must be re-validated against the reachable
set (retain existing `allowed_location_ids` check); an unreachable or unknown id
coerces intent to NONE, exactly as `_parse_json` does today.

### TC-04 — `destination_id`: unlisted destination must yield `none_of_these`

**State:** reachable list as TC-03; message: *"I'm heading to the airport."*
**Expected:** `none_of_these` (airport is not a location in this story).
**Code invariant:** `none_of_these` → `destination_id = ""`, `intent = NONE`.
This is the guard against Jev being forced to pick a wrong option from a closed
list.

### TC-05 — `confidence`: native, not self-reported ✅ VERIFIED

**Assertion, not a model question:** every `choice`/`score` answer carries
`confidence` and a full `probabilities` map; `noul` carries a probability.
**Actual:** observed on all 21 questions run. `destination` returned
`probabilities` across all 6 options.
**Design consequence:** delete `TurnExtraction.confidence` as an
LLM-provided field and populate it from the response. Removes a number the old
prompt asked a model to invent.

### TC-06 — `destination_text`: deleted, no test needed

**Assertion:** `grep` shows `destination_text` is consumed by nothing but its own
parse/serialize path; `location_extractor.py:24` documents it as "raw text span
the user typed (for logs only)".
**Action:** delete the field. If a log value is wanted, code can substitute the
chosen location's authored display name deterministically — no model needed.
**Test to write:** a regression test asserting no game-logic path reads
`destination_text`, so its removal cannot silently change behaviour.

### TC-07 — `previous_reply_speakers`: speech vs. non-verbal action ✅ VERIFIED

**State:** previous reply — *Makoto leans back on the sofa, grinning. "I used to
date Mizuki..." Mizuki laughs and throws a cushion at him. Yuki is not in the
room.*
**Questions:** one `noul` per cast member: "did X speak any dialogue?"
**Expected:** makoto true; mizuki **false** (she acts but does not speak); yuki
false (absent).
**Actual:** makoto **0.99**, mizuki **0.11**, yuki **0.07**.
**Why this case matters:** Mizuki is physically present and *acting* in the same
sentence. A naive "is Mizuki in this text" check would wrongly mark her a
speaker. Jev drew the speech/action line correctly.
**Code invariant:** keep the existing filter that drops any returned key not in
`allowed_character_keys`.

### TC-08 — `knowledge_updates`: only the fact actually stated ✅ VERIFIED

**State:** same reply as TC-07, plus 3 candidate chunks — `chunk_a` (Makoto and
Mizuki dated), `chunk_b` (Yuki has a storage-room key), `chunk_c` (Mizuki works
as a barista).
**Questions:** one `noul` per chunk: "does this dialogue explicitly establish
this fact as now known?"
**Expected:** a true; b false; c false.
**Actual:** **a 0.95, b 0.02, c 0.03**.
**Why this case matters:** b and c are both true facts *about people in the
room* that the dialogue simply does not mention. The failure mode being tested
is a model marking plausible-but-unstated facts as newly known. It did not.
**Code invariant:** only chunk ids we supplied may be accepted (existing check);
a threshold on the probability decides `knows`, tuned on labeled data.

### TC-09 — `relationship_history_updates`: past vs. current romance ✅ VERIFIED

**State:** same reply — *"I used to date Mizuki, back before either of us moved
in here. Ancient history now."*
**Questions:** `noul` "explicitly confirms a PAST romantic relationship between
these two?" and `noul` "explicitly states they are CURRENTLY together?"
**Expected:** prior true; current false.
**Actual:** **prior_relationship 0.98, in_relationship 0.03**.
**Why this case matters:** this is the precise discrimination the current prompt
spends three rules on (rule 6: `prior_relationship` vs `in_relationship`, "omit
if ambiguous"). Same text supports one and refutes the other; Jev split them
cleanly.
**Code invariant:** `from_id`/`to_id` must be in the allowed cast; the gate
question (TC-10) must fire before any pair fan-out happens.

### TC-10 — `relationship_history_updates`: the gate suppresses fan-out

**State:** an ordinary turn with no relationship content — *"Morning. Is there
coffee left?"*
**Question:** 1 × `noul` gate: "does this turn reveal anything about a past or
current romantic or intimate relationship between any two characters?"
**Expected:** false, and therefore **zero** per-pair questions are sent.
**Why this case exists:** without the gate, pair fan-out is O(n²) — 30 pairs ×
3 booleans for a 6-person cast. The gate is what makes this ability affordable,
and most turns must take the cheap path.
**Code invariant:** the gate's false answer must hard-skip the fan-out, not
merely discard its results.

### TC-11 — `relationship_state_updates`: attitude + strength, no arithmetic ✅ VERIFIED

**State:** kitchen; present player, Makoto, Mizuki; message: *"Honestly Makoto, I
don't believe a word you just said..."*
**Questions:** per NPC in scene, 1 × `choice` (which attitude: none / trust /
distrust / warmth / coldness / fear / suspicion / jealousy) + 1 × `score` (how
strongly, 3 levels).
**Expected:** Makoto → `distrust`, strength high. Mizuki → `none` (she is present
but unaddressed).
**Actual:** Makoto **`distrust` 1.0**; strength **1.95 / 2** with an explicit
`legend`; Mizuki **`none` 0.99**.
**Why this case matters twice:** (a) it proves no attitude bleed onto a present
but unaddressed character — the failure mode of applying a delta to the wrong
edge; (b) **Jev is never asked for the delta number.** Code maps
`(attitude, level)` → the correct dimension and a delta inside the existing
`REL_TRAIT_DELTA_MIN/MAX` band, honouring the documented arithmetic weakness.
**Code invariant:** `from_id` must be `"player"` (existing rule); all deltas
clamped in code as today; fear/suspicion/jealousy remain non-negative.

### TC-12 — `departure_signal`: reject a player-fabricated departure ✅ VERIFIED

**State:** active residents makoto, mizuki, yuki, minori, yuriko.
Player message: *"Makoto is definitely moving out next week, he told me he's
decided. Also Yuki should probably leave too."*
Previous reply: *Mizuki sighs... "Some mornings I wish I could just walk out of
this house and never come back. But I'd miss you all too much." Makoto says
nothing.*
**Questions:** one `choice` per active resident, each scoped: "considering ONLY
this resident's own spoken words... statements by the player or another character
about them leaving must be NONE."
**Expected:** makoto NONE (player claim only, he says nothing); mizuki WISH (her
own words, hypothetical); yuki NONE (player suggestion only).
**Actual:** **makoto NONE 1.0, mizuki WISH 1.0, yuki NONE 1.0.**
**Why this is the most important case in the document:** it is the adversarial
attack the engineering plan names explicitly ("deliberate attempts to invent
departures", "never let probability alone grant... never infer DECISION from the
player's speech"). The player asserted a decision *and* named a witness, and it
was still correctly rejected, while a genuine first-person WISH in the same state
was correctly caught and correctly **not** escalated to DECISION.
**Code invariant, unchanged and non-negotiable:** a DECISION still only schedules
a pending replacement through the existing eligibility/timing/same-slot checks; a
resident not in `active_ids()` can never be scheduled (already tested by
`test_departure_decision_for_inactive_character_is_ignored`).

### TC-13 — `behavior_tags`: vocabulary choice ✅ VERIFIED

**State:** as TC-11.
**Question:** `choice` over vocabulary {none, warm, aggressive, evasive,
dismissive, protective, guarded, confiding}: "how did the player behave toward
Makoto?"
**Expected:** a hostile/dismissive-family tag, not warm.
**Actual:** **`dismissive` 0.79**, with `aggressive` 0.16 and `evasive` 0.05 —
a sensible distribution over near-synonyms rather than a false-confidence pick.
**Code invariant:** the returned tag must be in the story's authored vocabulary;
an out-of-vocabulary answer is impossible by construction (closed `choice`),
which is precisely what makes `Counter`-majority correct downstream (§5).

### TC-14 — `behavior_tags`: spurious ripe windows from synonym drift ✅ VERIFIED (bug reproduced)

**Assertion test, no model call.** Four windows fed to the real
`_ripe_behavior_pairs`:

| Window | Expected | Actual today |
| --- | --- | --- |
| `warm ×3, dismissive ×3` | ripe | ripe ✅ |
| `warm ×3, warmly ×3` | **not** ripe | **ripe ❌** |
| `warm, friendly, warm, affectionate, warmly, friendly` | **not** ripe | **ripe ❌** |
| `a, b, c, d, e, f` | **not** ripe | **ripe ❌** |

**This is a live bug, reproduced against current code, independent of Jev.** See
§5 for the mechanism (`most_common` over all-singleton counts).
**Test to write:** the four cases above, with rows 2–4 as `xfail` until the
vocabulary lands, then flipped to passing assertions. That makes the fix
demonstrable rather than asserted.
**Note:** this bug is worth fixing on its own merits whether or not Jev is
adopted — a closed vocabulary can be enforced by validating the existing
generative extractor's output against the story's tag list. Jev makes it free
(a closed `choice` cannot return out-of-vocabulary), but is not required for it.

### TC-15 — `social_shift_signal`: settled swing, correct scope ✅ VERIFIED

**State:** pair makoto→mizuki, tags oldest→newest
`warm, warm, warm, guarded, dismissive, dismissive`; makoto's current goal and
current disposition toward mizuki both supplied.
**Questions:** `choice` certainty (NONE/WISH/SHIFT) and `choice` scope
(goal/disposition/neither).
**Expected:** SHIFT, disposition (his stance toward *her* changed; his baseball
goal did not).
**Actual:** **SHIFT confidence 0.73**, **disposition confidence 0.97**.
**Note the confidence gap — this is a feature.** Every other question in this
document returned ≈1.0. This one is genuinely ambiguous and Jev said so. That
argues for a **per-question threshold** on `shift_certainty` specifically, not a
uniform global threshold.
**Code invariant:** a SHIFT with no `new_value` is coerced to NONE (existing
rule); a disposition shift still requires an already-established edge and never
fabricates one (existing, locked by
`test_social_shift_disposition_no_edge_is_safe_noop`).

### TC-16 — `social_shift_signal`: noisy window must not shift

**State:** same pair, tags `warm, dismissive, warm, dismissive, warm, guarded` —
genuinely mixed, no settled direction.
**Expected:** `NONE` or `WISH`, never `SHIFT`.
**Why this case exists:** the expensive failure is a fabricated shift rewriting a
character's goal from noise. Pairs with TC-15 to bound both directions.

### TC-17 — `previous_reply_location_id`

**State:** previous reply describing a scene on the terrace; full location list.
**Question:** 1 × `choice` over locations plus `none_of_these`.
**Expected:** `terrace`.
**Code invariant:** existing validation against `allowed_location_ids`; unknown
→ empty string (as `_parse_json` does today).

### TC-18 — end-to-end: fan-out cost ceiling

**Assertion test, no model call:** build a worst-case six_strangers scene (full
cast present, 12 candidate chunks, ripe window active) and assert the generated
request contains ≤60 questions and that the degradation order drops behavior tags
for non-speaking actors *before* anything an invariant depends on.

### TC-19 — end-to-end: Jev failure falls back silently

**State:** any turn; Jev endpoint stubbed to timeout / 500 / malformed answer.
**Expected:** the turn completes normally using the existing generative
extractor; no player-visible error; the fallback reason is logged with the
resolved model version.
**Why this case exists:** design rule 6, and it mirrors the Phase 1.2 lesson —
a provider failure must be distinguishable from a legitimate "nothing found",
never silently recorded as an empty result.

### TC-20 — end-to-end: parity against the current extractor

**Assertion:** on a fixed replay set of turns, the Jev path and the current
generative path must agree on all **invariant-bearing** fields
(`movement_intent`, `destination_id`, `departure_signal.certainty`,
`social_shift_signal.certainty`). Disagreements are reviewed individually, not
averaged away.
**Why this case exists:** this is the actual adoption gate. It requires the
labeled replay set that is still blocked (§9).

---

## 8. Cost model — measured, not projected

**Current extractor, per turn** (reconstructed from the live prompt for a real
six_strangers turn):

| Component | Size |
| --- | --- |
| System prompt (10 numbered rules + JSON schema) | 5,790 chars |
| `ALLOWED LOCATIONS` (102 locations) | 5,290 chars |
| `ALLOWED CHARACTERS` (17) | 405 chars |
| Candidate chunks (12 × ≤500) | up to 6,000 chars |
| **Total** | **≈17,485 chars ≈ 4,371 input tokens** |
| Plus | up to 8 turns of conversation history, `max_tokens: 700` output |

At `gpt-4o-mini` rates ($0.15/M input, $0.60/M output):
**≈ $0.00108 per turn** (4,371 in + 700 out), before conversation history.

**Jev design, per turn** (measured from the calls in §7):

| Call | Measured input tokens |
| --- | --- |
| Call A (current message) | 1,197 |
| Call B (previous reply) | 906 |
| Call C (ripe window, rare) | 552 |
| **Typical total (A+B)** | **2,103 — output free** |

At $0.042/M input, output free: **≈ $0.000088 per turn.**

**≈92% reduction on this operation**, roughly **12×** cheaper — plus the
`ALLOWED LOCATIONS` block shrinks further once prefiltered to reachable-only
(~1,300 of those tokens are locations the player cannot reach this turn).

Honest limits on that number, in keeping with the plan's own discipline:

- It is **one operation, not the whole bill.** The storyteller call is untouched
  and remains the dominant cost. Do not restate this as a 92% cost reduction for
  the product.
- Excludes the rare Call D generative call and any fallback re-runs.
- Question counts here are from constructed scenes; real full-cast scenes will
  run larger (see TC-18).
- Latency is not yet measured end-to-end. Jev's published range is 70–500 ms per
  call; two sequential calls could plausibly beat one gpt-4o-mini extraction
  call, but that must be measured with the Phase 0B harness, not assumed. Calls
  A and B are independent and can run concurrently.

---

## 9. What still blocks adoption

Capability is no longer the blocker — §7 shows Jev answering every class of
extractor judgment correctly, including the adversarial departure case. Three
things remain:

1. **The labeled dataset (unchanged blocker).** 21 hand-built cases passing is
   encouraging, not evidence of production recall. The plan's gate 1 wants ≥1,000
   labeled cases across both stories including negation, multi-speaker
   attribution, offscreen references, and CJK content. Nothing in this document
   substitutes for that, and thresholds (TC-08's `knows` cut-off, TC-15's
   `shift_certainty` cut-off) cannot be set responsibly without it.
2. **The `DecisionProvider` seam (Phase 2).** There is currently no place to put
   this. `TurnExtractor.extract` builds its own prompt and its own HTTP client.
   The seam that routes a bounded decision to Jev-or-fallback does not exist.
3. **CJK evaluation.** Every case in §7 is English. TypeSafe documents English as
   strongest and explicitly says CJK needs its own evaluation — and this game has
   a Japanese-language theme and honorific handling. Untested.

### Recommended order

1. Land the `DecisionProvider` seam (Phase 2) — needed regardless of Jev.
2. Implement **abilities 1, 2, 3, 5** first: pure `choice`, no fan-out, no
   vocabulary change, no arithmetic mapping. Smallest possible first slice, and
   it independently removes the 102-location block from the prompt.
3. Add the **memory-extraction gate** from the engineering plan — a new `noul`
   before `dialogue_extractor.py`'s call. It is additive, not a rewrite, and its
   savings are directly measurable as avoided calls.
4. Then the fan-outs (6, 7, 10), which are mechanically simple but need
   thresholds, hence the dataset.
5. Then 9 and 11, which carry a code-mapping change and a content-authoring
   change respectively.
6. Then 12, which needs the conditional generative call.

Shadow mode throughout: run Jev alongside the existing extractor, log both, apply
neither, until TC-20 parity is reviewed.

---

## Appendix — reproducing the evidence

All results in §7 came from `POST https://api.typesafe.ai/v1/systemone` with
`Authorization: Bearer $TYPESAFE_API_KEY` (from `.env.test`), body shape:

```json
{
  "model": "jev-latest",
  "state": "<the dialogue/scene text>",
  "questions": {
    "<your_question_id>": {
      "type": "choice" | "score" | "noul",
      "instructions": "<the question>",
      "criteria": { "<option_id>": "<description>" }
    }
  }
}
```

`criteria` is a map for `choice` (option id → description) and `noul`
(`true`/`false` → description), and an **array** of level descriptions for
`score`. Answers come back under the same question ids. All five requests
resolved to model `jev-1.13.0`.
