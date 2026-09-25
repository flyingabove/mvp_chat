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
    get_typesafe_api_key,
    get_typesafe_model,
    is_typesafe_enabled,
)

# --- OpenAI / model config ---
# OPENAI_BASE_URL / OPENAI_MODEL route every non-storyteller model call
# (turn/location/knowledge extractors, translation). Defaults are the
# production values; the arena's offline local mode points them at Ollama
# (http://127.0.0.1:11434/v1, e.g. llama3.1:8b) so a locally started game
# makes no cloud calls.
import os as _os
OPENAI_API_KEY: str = get_openai_api_key()
OPENAI_BASE_URL: str = _os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL: str = _os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# --- Story master config ---
# "Story master" = the AI that generates NPC/narrator responses.
# Defaults to the OpenAI endpoint/key/model above. Override via env vars to
# point at a local Ollama instance (http://localhost:11434/v1) or any other
# OpenAI-compatible backend.
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

# --- TypeSafe AI / Jev (optional bounded-decision model, Phase 4 of the
# reuse/performance engineering plan) ---
# Same pattern as LangSmith above: key lives in .env.test / Railway env vars,
# read through credentials.py. Jev routing stays OFF unless TYPESAFE_ENABLED
# is explicitly truthy, so holding the key never silently reroutes a real
# decision through a third-party model. TYPESAFE_MODEL defaults to the
# "jev-latest" alias but should be pinned to a specific version (e.g.
# "jev-1.13.0") before any threshold-tuned production use - see the plan's
# Jev section for why a moving alias is unsafe once tuning begins.
TYPESAFE_API_KEY: str = get_typesafe_api_key()
TYPESAFE_MODEL: str = get_typesafe_model()
TYPESAFE_ENABLED: bool = is_typesafe_enabled()

# --- Jev rollout flags and tuning knobs (JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §7) ---
# Plain os.getenv tunables, not secrets - same pattern as STORY_MASTER_BASE_URL
# above. Per-task allowlists are CSV strings parsed at the call site, not here,
# so a "*" wildcard and an empty string both stay simple string comparisons
# rather than needing a parsed-list constant that's easy to get stale.
JEV_ENABLED_TASKS: str = _os.getenv("JEV_ENABLED_TASKS", "")       # "" = no task live
JEV_SHADOW_TASKS: str = _os.getenv("JEV_SHADOW_TASKS", "")         # "" = no task shadowed
JEV_SHADOW_SAMPLE_RATE: float = float(_os.getenv("JEV_SHADOW_SAMPLE_RATE", "0.0"))
JEV_TIMEOUT_MS: int = int(_os.getenv("JEV_TIMEOUT_MS", "1000"))
JEV_MAX_QUESTIONS_PER_BATCH: int = int(_os.getenv("JEV_MAX_QUESTIONS_PER_BATCH", "60"))

# Dynamic memory selection is a separate opt-in Jev task. It is active only
# when TYPESAFE_ENABLED is true AND JEV_ENABLED_TASKS includes
# "context_selection" (or "*"). The exponent sharpens optional-memory draws:
# 1.0 preserves utility weights, 1.5 is the default moderate preference, and
# 2.0 squares them. Required game facts never pass through this sampler.
JEV_CONTEXT_SELECTION_ALPHA: float = float(_os.getenv("JEV_CONTEXT_SELECTION_ALPHA", "1.5"))
JEV_CONTEXT_CANDIDATE_LIMIT: int = int(_os.getenv("JEV_CONTEXT_CANDIDATE_LIMIT", "200"))
JEV_CONTEXT_OPTIONAL_LIMIT: int = int(_os.getenv("JEV_CONTEXT_OPTIONAL_LIMIT", "6"))
JEV_CONTEXT_MIN_RELEVANCE: float = float(_os.getenv("JEV_CONTEXT_MIN_RELEVANCE", "0.35"))

# --- Jev circuit breaker parameters (JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §6) ---
JEV_BREAKER_FAIL_THRESHOLD: int = int(_os.getenv("JEV_BREAKER_FAIL_THRESHOLD", "3"))
JEV_BREAKER_FAIL_WINDOW_S: float = float(_os.getenv("JEV_BREAKER_FAIL_WINDOW_S", "60"))
JEV_BREAKER_FAIL_RATE_COUNT: int = int(_os.getenv("JEV_BREAKER_FAIL_RATE_COUNT", "5"))
JEV_BREAKER_COOLDOWN_S: float = float(_os.getenv("JEV_BREAKER_COOLDOWN_S", "30"))
JEV_BREAKER_COOLDOWN_MAX_S: float = float(_os.getenv("JEV_BREAKER_COOLDOWN_MAX_S", "300"))

# --- Integration test run counts (used by multi-run scenarios via _integ_run_count()) ---
# X: number of runs per multi-run scenario when running locally (no RAILWAY_* env vars)
# Y: number of runs per multi-run scenario when running on Railway
LOCAL_INTEG_RUN_COUNT: int = 5
PROD_INTEG_RUN_COUNT: int = 5
