# app/config.py
from __future__ import annotations

from backend.app.config.credentials import (
    get_openai_api_key,
    get_google_client_id,
    get_google_client_secret,
    get_jwt_secret,
    get_langsmith_api_key,
    get_langsmith_project,
    is_langsmith_enabled,
)

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

# --- Phase 3 "Social life": behavior-tag accumulation window ---
# How many recent behavior_tags per character pair before the engine
# considers asking the extractor to judge whether a genuine shift occurred.
BEHAVIOR_LOG_RIPE_THRESHOLD: int = 5
# Cap on how many tags are retained per pair (oldest evicted first).
BEHAVIOR_LOG_WINDOW_SIZE: int = 8
# How many of the most recent tags count as the "recent" half when checking
# for a majority swing vs. the tags before them.
BEHAVIOR_LOG_RECENT_SPAN: int = 3

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
# Credentials route through `credentials.py`, which falls back to .env.test when
# the env var is missing. Railway/CI env vars always take priority.
GOOGLE_CLIENT_ID: str = get_google_client_id()
GOOGLE_CLIENT_SECRET: str = get_google_client_secret()
JWT_SECRET: str = get_jwt_secret()
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRY_DAYS: int = 365

# --- LangSmith tracing (optional observability) ---
# Key lives in .env.test locally / Railway env vars in beta+prod, read through
# credentials.py like every other secret. Tracing stays OFF unless
# LANGSMITH_TRACING is explicitly truthy, so player content is never shipped to
# an external service just because the key is present.
LANGSMITH_API_KEY: str = get_langsmith_api_key()
LANGSMITH_PROJECT: str = get_langsmith_project()
LANGSMITH_TRACING_ENABLED: bool = is_langsmith_enabled()

# --- Integration test run counts (used by multi-run scenarios via _integ_run_count()) ---
# X: number of runs per multi-run scenario when running locally (no RAILWAY_* env vars)
# Y: number of runs per multi-run scenario when running on Railway
LOCAL_INTEG_RUN_COUNT: int = 5
PROD_INTEG_RUN_COUNT: int = 5
