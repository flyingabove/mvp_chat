# Realistic first meetings: what is left (engine first, Terrace configures)

**Principle (owner, 2026-09-30, softened 2026-10-01):** prefer generic mechanisms on the Character / relationship /
world-model objects, with Terrace configuring them. A Terrace-only mechanic is a strongly discouraged last resort, not
forbidden. Design: [design/TERRACE_HOUSE.md §11-12](../design/TERRACE_HOUSE.md); as built: the acquaintance
ladder, affinity signals and the group ritual in [design/SOCIAL_ENGINE.md](../design/SOCIAL_ENGINE.md). NPC initiative
gated on acquaintance and stance, group energy from temperament and third-party reads moved into
[BL-85](BL-85-character-social-mind.md); deadpan humor as a style moved into the `drama` profile of
[BL-87](BL-87-drama-direction-knobs.md) (2026-10-01).

## BL-76 — Reaction cues and model warmth still outrun relationship state
- **Bucket:** C (engine)
- **Open:** (a) `turn.reaction_cues` still says "responds warmly" at every acquaintance level. (b) Stock warmth ("eyes sparkling", "friendly smile") and the persona name before it was given leaked on the local 8B model (2 in 12 turns); it is unmeasured on Gemini + Jev, and whether affinity signals (`world_model/signals.py`) read as ambiguous rather than flirtatious has never been checked on a hosted run (absorbed from BL-84).
- **Next:** word reaction cues from the person's level (polite, pleased, at strangers); make the harness name consistent. One hosted run on Gemini + Jev (free, no approval needed, AGENTS.md section 4) measures the leak rate and reads the signal turns against BL-87 rubric item S4. Only if prompting is not enough, add a post-check that regenerates replies containing stock closeness for strangers; hold it to the >=99% rule in `user_corrections.md` (semantic, via Jev, never a regex alone).
- **Touches:** `world_model/turn.py` (`CUE_TEXT`), `world_model/signals.py` (wording only if the read is wrong), `scripts/terrace_ollama_sim.py`.
