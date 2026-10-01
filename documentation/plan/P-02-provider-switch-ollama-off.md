---
id: P-02
title: Provider switch - Gemini+Jev or OpenAI+Jev, Ollama off by default
stage: 0
size: S
depends_on: []
touches: [backend/app/config/settings.py, backend/app/llm/chat.py, scripts/terrace_ollama_sim.py, scripts/scorer/story_agent_ui.py, .claude/skills/promote-to-prod/arena/local_release.py, .claude/skills/promote-to-prod/SKILL.md, tests/backend/app/llm/]
backlog: BL-86
---
**Why (owner, 2026-10-01):** simulations and the debug tools use Gemini + Jev by default, OpenAI + Jev as the
alternative. The local Ollama path is switched off for now but must stay one switch away.

**Read first:** `documentation/backlog/BL-86-headless-season-simulation.md` (owner decisions), `backend/app/llm/chat.py`
(`resolve_chat_config`; provider is chosen by `LLM_PROVIDER`: gemini default, openai, ollama), the Ollama call sites in
`scripts/terrace_ollama_sim.py`, `scripts/scorer/story_agent_ui.py` and `.claude/skills/promote-to-prod/arena/local_release.py`.

**Build**
- A setting `OLLAMA_ENABLED` (env `OLLAMA_ENABLED`, default **false**). While false: `LLM_PROVIDER=ollama` and every
  Ollama-only entry point fail fast with one clear message ("Ollama is switched off; set OLLAMA_ENABLED=1") instead of
  trying to connect. Production behaviour is unchanged (it never uses Ollama).
- Failing tests first: provider resolution with the switch off rejects `ollama` and still resolves gemini/openai; the
  three scripts refuse to start while it is off and start when it is on.
- Document the switch next to the provider note in `design/PLATFORM.md` (env var list) and in
  `design/SOCIAL_ENGINE.md` where the offline sim is described.

**Promotion precheck:** `/promote-to-prod` runs a free offline Ollama precheck; it must set `OLLAMA_ENABLED=1` explicitly for that
step (update `SKILL.md` and `local_release.py`), so promotions keep working while the default stays off.

**Done when:** tests pass; the default environment cannot reach Ollama; `OLLAMA_ENABLED=1` restores today's behaviour.

**Note:** does not close BL-86 (that is the season runner); update its "Next" line to remove the switch.
