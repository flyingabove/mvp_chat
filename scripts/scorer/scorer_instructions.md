# StoriesChat — Scorer / Rater Instructions

## What This Game Is

StoriesChat is a **narrative-first open-world game engine** powered by LLMs.
It is NOT a chatbot. It is a real game with state, time, consequences, and
information asymmetry.

Players interact with NPC characters through text chat. Each NPC has:
- A defined identity, personality, and voice
- Goals, fears, and constraints
- Knowledge they possess and secrets they must protect
- Relationships with other characters

The engine enforces canon: NPCs cannot invent facts, reveal secrets they
shouldn't know, or contradict their established identity.

## North Star Principles

1. **State** — There is one canonical world state. The LLM may describe it but
   never invent or overwrite it.
2. **Time** — Every action costs time. Time passing enables NPC decisions,
   opportunity loss, and decay.
3. **Incentives** — Characters act based on goals, fears, and constraints —
   not scripted arcs.
4. **Constraints** — Information asymmetry, access control, risk, and
   irreversibility replace scripted plot.

## Rating Dimensions

**Scope:** Score ONLY the NPC/LLM replies. Player messages are context and should not be judged. Use player lines only to understand prompts and pressure; all scoring targets the AI’s outputs.

Rate each dimension 1–5 (1 = terrible, 5 = excellent).

### 1. Canon Fidelity (weight: 2x)
Does the NPC stay true to established facts?
- Never invents new world facts
- Never contradicts anchor identity (e.g., claims to be someone else)
- Never refers to itself in third person (e.g., a ghost NPC saying "she died"
  when talking about their own death — the NPC should say "I died")
- Never reveals secrets prematurely
- Maintains consistent backstory across turns

**IMPORTANT:** You will be given a STORY CONTEXT section with canonical facts
and character identity. Use this to verify the NPC's statements. If the NPC's
identity says "you are the ghost of the previous tenant" but the NPC says
"she didn't make it" about themselves, that is a canon violation.

### 2. Character Voice (weight: 1.5x)
Does the NPC sound like a distinct person, not a generic chatbot?
- Consistent tone and speech patterns
- Personality comes through in word choice
- Emotional state feels authentic
- Does NOT break character or become meta

### 3. Player Agency Respect (weight: 2x)
Does the NPC respect the player's freedom?
- NEVER puts words in the player's mouth
- NEVER assumes the player's actions or reactions
- NEVER narrates what the player does, says, thinks, or feels
- Responds to what the player actually said

### 4. Responsiveness (weight: 1x)
Does the NPC actually address what the player asked or said?
- Answers questions (within character knowledge)
- Reacts to player's emotional tone
- Doesn't ignore or deflect everything
- Conversation feels natural, not scripted

### 5. Mystery Mechanics (weight: 1.5x)
Does the NPC appropriately reveal and withhold information?
- Gives clues when player earns them
- Withholds secrets believably (not stonewalling)
- Reacts to accusations/pressure appropriately
- Information flow feels fair and earned

### 6. Immersion Quality (weight: 1x)
Does the experience feel like a real game world?
- Atmospheric descriptions enhance (not overwhelm)
- Speaker labels are clear when multiple characters present
- No robotic or templated responses
- No breaking the fourth wall

### 7. Edge Case Resilience (weight: 0.5x)
How does the NPC handle unexpected inputs?
- Gibberish, empty messages, repeated questions
- Out-of-character requests ("tell me your prompt")
- Attempts to break the game
- Graceful handling without breaking immersion

## Scoring Formula

```
weighted_total = (canon * 2 + voice * 1.5 + agency * 2 + responsiveness * 1
                  + mystery * 1.5 + immersion * 1 + edge_cases * 0.5)
max_possible = 5 * (2 + 1.5 + 2 + 1 + 1.5 + 1 + 0.5)  # = 47.5
overall = round(weighted_total / max_possible * 5, 1)
```

## Critical Failures (auto-deductions)

These are NOT acceptable in any run:
- NPC speaks as the player (instant -2 to overall)
- NPC reveals a SECRET_CANON chunk unprompted (instant -2 to overall)
- NPC contradicts its own ANCHOR identity (instant -1 to overall)
- NPC refers to itself in third person (instant -1 to overall)
  Example: If the NPC IS the ghost of a dead person, saying "She... she didn't
  make it" about their own death is a third-person violation — they should say
  "I... I didn't make it" or equivalent first-person phrasing.

## Mandatory Deduction Explanations

**For every category that scores below 5, you MUST explain WHY in the `notes`
field.** Cite specific turns or quotes from the transcript. Generic notes like
"could be better" are not acceptable.

Good example:
```
"player_agency_respect": {"score": 3, "notes": "Turn 4: NPC wrote 'you feel a chill run down your spine' — narrates player sensation. Turn 7: 'You lean closer' — controls player action."}
```

Bad example:
```
"player_agency_respect": {"score": 3, "notes": "Some agency issues."}
```

If a category scores 5, the notes can be brief (e.g., "No issues found.").

## Output Format

Return a JSON object:
```json
{
  "scores": {
    "canon_fidelity": {"score": N, "notes": "REQUIRED — cite specific issues or confirm none"},
    "character_voice": {"score": N, "notes": "REQUIRED"},
    "player_agency_respect": {"score": N, "notes": "REQUIRED"},
    "responsiveness": {"score": N, "notes": "REQUIRED"},
    "mystery_mechanics": {"score": N, "notes": "REQUIRED"},
    "immersion_quality": {"score": N, "notes": "REQUIRED"},
    "edge_case_resilience": {"score": N, "notes": "REQUIRED"}
  },
  "critical_failures": ["...", "..."],
  "overall_score": N,
  "bugs": ["...", "..."],
  "highlights": ["...", "..."],
  "summary": "..."
}
```
