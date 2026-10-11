# Smarter, self-interested characters: what BL-85 does not cover (generic engine)

**Principle (owner, 2026-09-30):** these items improve the *game engine's* characters for every story; Terrace only
configures them. Goals, strategies (scheming, safe_pick), planfulness/candor consumers, NPC confession as a want,
fallout as stance rules, claim intent, staged talk and watching all moved into
[BL-85](BL-85-character-social-mind.md) (2026-10-01). Design background: [design/TERRACE_HOUSE.md §12](../design/TERRACE_HOUSE.md).

## BL-81 — Asynchronous off-screen thinking for any character (generic)
- **Bucket:** C (engine)
- **Plan:** P-15 (blocked by P-11); do not start it separately.
- **Open:** NPC reasoning happens only inside a turn, so a character cannot carry out a plan deeper than one turn allows. BL-85 gives each character short- and long-term plans (horizon from `planfulness`) and wants such as `stage_talk`/`watch`; this item is how multi-step plans are *executed*.
- **Next:** after a turn's bounded decision step, start a background job when a trigger fires (a confession, a betrayal opening, a rival noticing interest). The job writes a plan of concrete, physically executable steps (talk to X, call Y, go to a room, plant a rumor) that executes unless the player acts first. No telepathy: every step uses a conversation, a call or a location. Needs job persistence across saves and deploys, a cost cap, and determinism in tests.
- **Touches:** `world_model/` (agendas, plans), a new job runner, `prompt_engine.py`, `design/WORLD_MODEL.md`.

## BL-82 — High-stakes act outcomes: delayed answers and the leave-together fallout
- **Bucket:** C (engine)
- **Plan:** P-14 (blocked by P-11); do not start it separately.
- **Open:** (a) no "still thinking" answer that comes back after days, during which a rival can ask first; (b) Jev's verdict options are still accept / not yet / reject, with no "let me think"; (c) declined-act fallout covers `confess` only, not `ask_leave_together`, and the finale panel does not yet use these events (`ask_leave_together_declined` is listed in `commentary.FOOTAGE_KINDS`; verify an event is actually emitted for it).
- **Next:** a `pending_answer` record (act, target, due day) resolved later by the target's own stances and strategy (BL-85: `safe_pick` prefers whoever stands highest with them); add `defer` to the verdict options; apply fallout to `ask_leave_together` and add declined acts to the finale dossier.
- **Touches:** `world_model/social_acts.py`, `act_fallout.py`, `npc_decision.py`, `commentary.py`.
