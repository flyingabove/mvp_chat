# BL-43 — Name and nickname matching should be Jev's judgment, under the 99% rule

- **Type:** follow-up
- **Found:** 2026-09-29, owner direction during the promise-completion rework
- **Severity:** medium; a missed match silently drops a fact or promise that the player did state.

## Problem
Several trackers decide "is this the same person/thing?" with string rules: `world_model/speakers.py` `addressed_ids` / `_name_terms` (who a message names), `world_model/commitments.py` `_words` / `DUPLICATE_OVERLAP` in `record_commitment` (near-duplicate promises), `memory.py` mention matching. Nicknames ("Ri-chan", "Uchi" for Tatsuya Uchihara), transliterations and pronouns defeat them. The owner's rule (see `documentation/user_corrections.md` 2026-09-29): forgetting is acceptable, failing to register something that happened is not; semantic dedup belongs to Jev, and a matcher that cannot reach ~99% on the missed-match direction should be removed in favour of conversation context.

## Fix direction
Follow `documentation/proposals/PROMISE_COMPLETION_JEV_2026_09_29.md`: one bounded Jev question per ambiguous match (a choice or yes/no through `npc_decision.build_resolver`), uncertainty resolving toward "same" where a false match only forgets, a labeled dev set plus a never-tuned held-out set with `scripts/eval/`-style measurement, and deletion of the string rule if the miss rate stays above 1%. Start with `addressed_ids` (nickname addressed vs. mentioned) and the duplicate-promise check in `record_commitment`.

## Touches
`backend/app/engine/world_model/speakers.py`, `commitments.py`, `memory.py`, `npc_decision.py` (`build_resolver`), new eval script and labeled cases under `tests/data/`.
