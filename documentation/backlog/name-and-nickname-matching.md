# Name and nickname matching

## BL-43 — Name and nickname matching should be Jev's judgment under the 99% rule
- **Open:** string rules decide "same person or thing": `world_model/speakers.py` `addressed_ids`/`_name_terms`, `commitments.py` `_words`/`DUPLICATE_OVERLAP` in `record_commitment`, `memory.py` mention matching. Nicknames ("Ri-chan", "Uchi") and transliterations defeat them.
- **Next:** one bounded Jev question per ambiguous match through `npc_decision.build_resolver` (`noul` criteria may be a list: `jev.py` `_build_criteria` converts it to the `{"true","false"}` map the API requires), uncertainty resolving toward "same" where a false match only forgets, a labeled dev set plus an untouched held-out set (pattern: `scripts/eval/promise_judge_eval.py`, cases in `tests/eval_cases/`), integration test never run on deploy, string rule deleted if the miss rate stays above the gate. Start with `addressed_ids` and the duplicate-promise check.
