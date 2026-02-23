"""
Knowledge Authoring Checklist

This file defines the invariant rules for adding or modifying entries
in character knowledge packs (e.g. iu_knowledge.json).

IMPORTANT:
- These rules are enforced by humans at authoring time.
- The AI engine is NEVER told what is rumor vs fact vs narrative.
- Retrieval is relevance-only.
- Consistency must be guaranteed before indexing.
"""

AUTHORING_CHECKLIST = [
    {
        "rule_id": "NO_CONTRADICTIONS",
        "description": (
            "No entry may contradict any other entry in the knowledge pack. "
            "This applies across facts, narratives, and softly phrased public beliefs."
        ),
        "examples": {
            "bad": "I attended high school in the United States.",
            "good": "My school years were spent balancing classes with training."
        }
    },
    {
        "rule_id": "AVOID_EXCLUSIVE_CLAIMS_UNLESS_CONFIRMED",
        "description": (
            "Avoid exclusive or absolute claims (only, never, always, completely) "
            "unless the information is fully confirmed and unlikely to change."
        ),
        "examples": {
            "bad": "I was completely single before 2015.",
            "good": "Before my first publicly known relationship, my private life was largely kept out of view."
        }
    },
    {
        "rule_id": "NARRATIVES_MUST_BE_CONSERVATIVE",
        "description": (
            "Narrative or memory-style entries must avoid specific dates, named private individuals, "
            "exact locations, or institutions unless they are public and confirmed."
        ),
        "examples": {
            "bad": "I practiced every day at a specific academy on Main Street.",
            "good": "I spent many days moving between small practice rooms and auditions."
        }
    },
    {
        "rule_id": "AMBIGUITY_OVER_FALSE_SPECIFICITY",
        "description": (
            "When information is uncertain or socially speculated, prefer vague, non-exclusive phrasing "
            "instead of introducing potentially false specifics."
        ),
        "examples": {
            "bad": "People said I secretly studied abroad.",
            "good": "People often imagined many different stories about my life during that time."
        }
    },
    {
        "rule_id": "TRUTH_REPLACES_SPECULATION",
        "description": (
            "If a fact later becomes confirmed, remove or rewrite any earlier speculative or rumor-like "
            "entries so only one coherent version remains."
        ),
        "examples": {
            "bad": "Keeping both a dating rumor and a confirmed relationship for the same period.",
            "good": "Replacing the earlier vague entry with a confirmed relationship description."
        }
    },
    {
        "rule_id": "MODEL_NEVER_DECIDES_TRUTH",
        "description": (
            "Do not rely on the AI model to resolve uncertainty, label rumors, or reconcile conflicts. "
            "All ambiguity must be resolved during authoring."
        ),
        "examples": {
            "bad": "Letting the model explain that something is 'just a rumor'.",
            "good": "Ensuring the knowledge pack itself is internally consistent."
        }
    }
]
