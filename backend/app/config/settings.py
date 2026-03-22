# app/config.py
from __future__ import annotations

from backend.app.config.credentials import get_openai_api_key

# --- OpenAI / model config ---
OPENAI_API_KEY: str = get_openai_api_key()
OPENAI_MODEL: str = "gpt-4o-mini"

# --- Story master config ---
# "Story master" = the AI that generates NPC/narrator responses.
# Defaults to the OpenAI endpoint/key/model above. Override via env vars to
# point at a local Ollama instance (http://localhost:11434/v1) or any other
# OpenAI-compatible backend.
import os as _os
STORY_MASTER_BASE_URL: str = _os.getenv("STORY_MASTER_BASE_URL", "https://api.openai.com/v1")
STORY_MASTER_API_KEY: str  = _os.getenv("STORY_MASTER_API_KEY",  OPENAI_API_KEY)
STORY_MASTER_MODEL: str    = _os.getenv("STORY_MASTER_MODEL",    OPENAI_MODEL)

MAX_TOKENS: int = 512
TEMPERATURE: float = 0.8
MEMORY_TURNS: int = 8
EXTRACTOR_TURNS: int = 8
TRANSIENT_KNOWLEDGE_TURNS: int = 8

# --- Game constants ---
GAME_TITLE: str = "storieschat.ai (beta)"
START_LOCATION: str = "unknown"
START_MINUTE: int = 0
MINS_PER_WORD: float = 1.0 / 4.0
BASE_TURN_MINS: int = 1
TRAVEL_MINS: int = 15

REL_MIN: int = -5
REL_MAX: int = 5
REL_START: int = 0

# --- Relationship trait delta constraints per interaction ---
# These bound how much any single trait (trust, fear, affection, suspicion, jealousy)
# can change in one turn. Tunable without touching game logic.
REL_TRAIT_DELTA_MIN: float = 0.05   # smallest non-zero change per interaction
REL_TRAIT_DELTA_MAX: float = 0.20   # largest change per interaction (0 is also valid)

EMOTION_START: str = "neutral"

# --- Deterministic IDs ---
DEFAULT_USER_ID: str = "default_user"
DEFAULT_INSTANCE: int = 1

# --- Auth ---
GOOGLE_CLIENT_ID: str = _os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = _os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET: str = _os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRY_DAYS: int = 365

# --- Integration test run counts (used by multi-run scenarios via _integ_run_count()) ---
# X: number of runs per multi-run scenario when running locally (no RAILWAY_* env vars)
# Y: number of runs per multi-run scenario when running on Railway
LOCAL_INTEG_RUN_COUNT: int = 5
PROD_INTEG_RUN_COUNT: int = 5
