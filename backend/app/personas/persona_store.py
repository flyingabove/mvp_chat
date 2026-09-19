from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_PERSONAS_PATH = Path(__file__).with_name("default_personas.json")


def _load_default_personas() -> dict[str, dict[str, Any]]:
    if not _DEFAULT_PERSONAS_PATH.exists():
        return {}
    try:
        raw = json.loads(_DEFAULT_PERSONAS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def get_default_persona(persona_id: str = "paul_dingus") -> dict[str, Any]:
    personas = _load_default_personas()
    if persona_id in personas:
        return dict(personas[persona_id])
    return {}


def get_default_persona_prompt_text(persona_id: str = "paul_dingus") -> str:
    persona = get_default_persona(persona_id)
    if not persona:
        return ""

    name = str(persona.get("name") or "Player").strip()
    gender = str(persona.get("gender") or "").strip()
    free_text = str(persona.get("free_text") or "").strip()

    parts = [f"Your default persona is {name}."]
    if gender:
        parts.append(f"Gender: {gender}.")
    if free_text:
        parts.append(f"Other attributes: {free_text}")
    return "\n".join(parts)
