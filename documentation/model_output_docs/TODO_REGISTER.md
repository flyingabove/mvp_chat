# TODO Register (Model Output Docs)

This file is a centralized register of active TODOs that currently affect runtime behavior, validation, or release confidence.

## Active TODOs

1. **IU identity correction integration is quarantined (expected-fail)**
   - **Status:** OPEN
   - **Priority:** HIGH
   - **Owner:** Epistemic/prompt runtime
   - **Where:** `tests/backend/integration/test_iu_identity_correction.py`
   - **Current behavior:** test remains fully executed but uses non-blocking TODO warning behavior when evaluator returns `FALSE`.
   - **Failure summary:** IU sometimes answers the prompt “what happened to the previous tenant?” as if IU and tenant are different people.
   - **Required fix:** enforce first-person identity correction in renderer behavior for this intent class and re-enable strict pass.
   - **Exit criteria:** restore strict assertion (`TRUE` required), run integration playback scenario repeatedly, verify stable TRUE verdict from evaluator.

2. **Truth vs belief enforcement utility remains incomplete**
   - **Status:** OPEN
   - **Priority:** HIGH
   - **Where:** `documentation/model_output_docs/EPISTEMIC_ENGINE_TODO.md`
   - **Needed:** comparator utility for truth precedence + explicit contradiction marking without auto-resolution.

3. **Prompt-layer caps are not hard-enforced**
   - **Status:** OPEN
   - **Priority:** MEDIUM
   - **Where:** `documentation/model_output_docs/NORTH_STAR_GAPS_AUDIT_2026-02-20.md`
   - **Needed:** fixed token budgets per epistemic layer to prevent lower-tier crowding.

4. **Belief-to-canonical promotion governance is missing**
   - **Status:** OPEN
   - **Priority:** MEDIUM
   - **Where:** `documentation/model_output_docs/EPISTEMIC_ENGINE_TODO.md`
   - **Needed:** audited promotion queue for repeated high-confidence claims.

## Update Rule

When a TODO is added, resolved, or re-scoped:
- Update this register in the same change set.
- Link to the source file/doc where implementation details live.
- If a test is quarantined (`xfail`/skip), include clear exit criteria and target owner.
