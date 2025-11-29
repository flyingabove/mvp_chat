# app/config.py
from __future__ import annotations
import os

# --- OpenAI / model config ---
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = "gpt-4o-mini"

MAX_TOKENS: int = 512
TEMPERATURE: float = 0.8
MEMORY_TURNS: int = 18

# --- Game constants ---
GAME_TITLE: str = "storieschat.ai (beta)"
START_LOCATION: str = "Nonhyeon-dong officetel"
START_MINUTE: int = 0
MINS_PER_WORD: float = 1.0 / 4.0
BASE_TURN_MINS: int = 1
TRAVEL_MINS: int = 15

REL_MIN: int = -5
REL_MAX: int = 5
REL_START: int = 0

EMOTION_START: str = "wary, exhausted"
