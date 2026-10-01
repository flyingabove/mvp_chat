# Realistic first meetings: what is left (engine first, Terrace configures)

**Principle (owner, 2026-09-30):** generic mechanisms on the Character / relationship / world-model objects; Terrace
only configures them. Design: [design/TERRACE_HOUSE.md §11-12](../design/TERRACE_HOUSE.md); as built: the acquaintance
ladder, affinity signals and the group ritual in [design/SOCIAL_ENGINE.md](../design/SOCIAL_ENGINE.md). NPC initiative
gated on acquaintance and stance, group energy from temperament and third-party reads moved into
[BL-85](BL-85-character-social-mind.md); deadpan humor as a style moved into the `drama` profile of
[BL-87](BL-87-drama-direction-and-script-rubric.md) (2026-10-01).

## BL-76 — Reaction cues and model warmth still outrun relationship state
- **Open:** (a) `turn.reaction_cues` still says "responds warmly" at every acquaintance level. (b) The local 8B model still leaks stock warmth now and then ("eyes sparkling", "friendly smile"; 2 in 12 turns) and the persona name before it was given ("Paul-san" on turn 1: the harness introduces the player as `Sam` while the default persona is Paul, so check the real default-persona flow too). Hosted Gemini has not been measured on this.
- **Next:** word reaction cues from the person's level (polite, pleased, at strangers); make the harness name consistent and check the leak rate on the hosted model. Only if prompting is not enough, add a post-check that regenerates replies containing stock closeness for strangers; hold it to the >=99% rule in `user_corrections.md` (semantic, via Jev, never a regex alone).
- **Touches:** `world_model/turn.py` (`CUE_TEXT`), `scripts/terrace_ollama_sim.py`.

## BL-84 — A spoken quote is split across segments; signal ambiguity unchecked on hosted
- **Open:** on live beta `4aedb46` (Gemini, 2026-09-30, 12 turns, guest) a quote was split across segments ("It is strange," / "Arman says," / "You forget it is there..."). Whether affinity signals read as ambiguous rather than flirtatious has not been checked on a hosted run.
- **Next:** a dialogue-segmentation regression that merges a quote interrupted only by a speech tag; one hosted run reading signal turns.
- **Touches:** `engine/dialogue.py`, `world_model/signals.py`.
