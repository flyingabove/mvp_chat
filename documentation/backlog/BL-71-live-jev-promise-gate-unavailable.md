# Live Jev promise gate availability

## BL-71 — Live promise-judge accuracy gate cannot reach Jev
- **Open:** On 2026-09-30, `tests/backend/integration/test_promise_judge_accuracy.py` failed twice on current beta because one Jev HTTP error opened the provider circuit and all 318 labeled answers were unusable (`skip:http_error` 1, `skip:circuit_open` 317). The offline deploy gate passed 1,626 tests. This prevents a full live-integration-suite pass for the iOS update repair; it does not exercise the frontend.
- **Next:** Check Jev service/account status and the first HTTP error without logging credentials, then rerun the single integration gate and full suite. If repeatable, repair the provider transport or evaluation retry behavior and retain a regression for the failure mode.
- **Touches:** `backend/app/llm/providers/jev.py`, `scripts/eval/promise_judge_eval.py`, `tests/backend/integration/test_promise_judge_accuracy.py` as diagnosis warrants.
