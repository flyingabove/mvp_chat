# User Corrections Log

> **What this doc is for:** Log of user corrections to prevent repeating mistakes. Edit this doc when the user corrects a mistake that should be remembered across sessions.

Patterns from user feedback to prevent repeating mistakes.

## 2026-03-08: Don't auto-push to production

**What happened:** After fixing SVG thumbnails and hero CSS, I pushed to both `beta` AND `main` (production) without asking.

**Rule:** Always push to `beta` first. Only merge to `main` when the user explicitly requests it. `main` triggers Railway auto-deploy — treat it as sacred.

**Added to:** CLAUDE.md section 8, MEMORY.md workflow preferences.

## 2026-03-12: Localhost is debugger-only

**What happened:** OAuth/login guidance included localhost callback assumptions, but user clarified localhost should only be used for debug tooling.

**Rule:** Treat localhost as debug/scorer-only (`/beta/debug`). App login and Google OAuth callbacks should be documented and configured for hosted domains.

**Added to:** `documentation/model_output_docs/AUTH_AND_PERSISTENCE_DESIGN.md`, `documentation/model_output_docs/INFRASTRUCTURE.md`.
