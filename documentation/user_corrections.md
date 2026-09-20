# User Corrections Log

> **What this doc is for:** Log of user corrections to prevent repeating mistakes. Edit this doc when the user corrects a mistake that should be remembered across sessions.

Patterns from user feedback to prevent repeating mistakes.

## 2026-03-08: Don't auto-push to production

**What happened:** After fixing SVG thumbnails and hero CSS, I pushed to both `beta` AND `main` (production) without asking.

**Rule:** Always push to `beta` first. Only merge to `prod` when the user explicitly requests it. `prod` triggers Railway production deploy — treat it as sacred.

**Added to:** CLAUDE.md section 8, MEMORY.md workflow preferences.

## 2026-03-12: Localhost is debugger-only

**What happened:** OAuth/login guidance included localhost callback assumptions, but user clarified localhost should only be used for debug tooling.

**Rule:** Treat localhost as debug/scorer-only (`/beta/debug`). App login and Google OAuth callbacks should be documented and configured for hosted domains.

**Added to:** `documentation/model_output_docs/AUTH_AND_PERSISTENCE_DESIGN.md`, `documentation/model_output_docs/INFRASTRUCTURE.md`.

## 2026-03-21: Use one canonical intermediate task file

**What happened:** Intermediate task tracking was spread across ad-hoc files/folders (`tasks/`), creating inconsistency and stale leftovers.

**Rule:** Intermediate execution tasks must be tracked in one canonical file: `documentation/plans_scratch/TASKS_INTERMEDIATE.md`. Agents must consume this file before non-trivial work, update it during execution, and clean up completed entries at task end.

**Added to:** `documentation/ai_learnings_mistakes/AI_TASK_WORKFLOW.md`, `documentation/AI_DOC_INDEX_CATALOGUE.md`, `.gitignore`.

## 2026-09-18: Human characters are personas; default persona is canonical and reuseable

**What happened:** User clarified that NPCs and player-controlled humans must be treated differently. The human character path is always a `persona`, not an NPC or a generic "player" avatar, and the app should support exactly two persona modes for now: a temp per-game persona and a built-in default persona.

**Rule:** Use the term `persona` for the human-controlled character layer, reserve `NPC`/`character` for story cast members, and default to the server-stored Paul Dingus persona unless the user chooses a temp persona. Keep the system reusable across both active games and avoid custom persona creation/storage in this pass.

**Added to:** `backend/app/personas/persona_store.py`, `backend/app/engine/state.py`, `frontend/index.html`.
