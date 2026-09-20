FROM python:3.10-slim

# ------------------------------------------------------------
# App setup
# ------------------------------------------------------------
ENV PYTHONPATH=/srv
ENV KNOWLEDGE_CACHE_DIR=/data/knowledge_cache
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBUG_MODE=FALSE

# Build-time secret — Railway passes this as a build arg so build-time
# tests (below) can call OpenAI. A11 fix: this must NOT be promoted to ENV.
# `ARG` values are available to subsequent RUN instructions in this same
# build stage automatically, but (unlike ENV) are not written into the
# final image's config/layer history, so the key never ends up embedded in
# the shipped image. The real runtime key is injected by the deployment
# platform (Railway service/environment variable), not by this build arg.
ARG OPENAI_API_KEY=""

# ------------------------------------------------------------
# Copy code (clean, deterministic)
# ------------------------------------------------------------
RUN echo "🔥 Resetting /srv and /tmp" \
    && rm -rf /srv \
    && rm -rf /tmp \
    && mkdir -p /srv \
    && mkdir -p /tmp \
    && chmod 1777 /tmp

WORKDIR /srv

COPY backend/ /srv/backend/
COPY frontend/ /srv/frontend/
COPY tests/ /srv/tests/
COPY scripts/ /srv/scripts/

# ------------------------------------------------------------
# Install dependencies
# ------------------------------------------------------------
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt

# Optional: log environment versions (safe, fast)
RUN python /srv/backend/app/knowledge/build/print_env_versions.py

# ------------------------------------------------------------
# BUILD-TIME DEBUG (pre-tests)
# ------------------------------------------------------------
RUN if [ "${DEBUG_MODE:-FALSE}" = "TRUE" ]; then \
      echo "================ BUILD-TIME DEBUG (BEFORE TESTS) ================"; \
      echo "🧪 ENVIRONMENT VARIABLES (filtered)"; \
      env | sort | grep -E '^(PYTHONPATH|KNOWLEDGE_CACHE_DIR|KNOWLEDGE_PERSIST_ROOT|FORCE_REBUILD_INDEX|RUN_TESTS|DEBUG_MODE)=' || true; \
      echo ""; \
      echo "🐍 Python / Pip"; \
      python -V; \
      pip -V; \
      echo ""; \
      echo "📦 Installed packages (top)"; \
      pip list | head -n 80 || true; \
      echo ""; \
      echo "📂 /data tree (build-time; note Railway volume mounts at runtime)"; \
      ls -la /data || true; \
      ls -la /data/knowledge_cache || true; \
      ls -la /data/knowledge_cache/characters || true; \
      ls -la /data/knowledge_cache/characters/ || true; \
      echo ""; \
      echo "📂 /srv/backend/app/knowledge/characters/ (image bundles)"; \
      ls -la /srv/backend/app/knowledge/characters/ || true; \
      echo ""; \
      echo "📂 /tmp tree (build-time)"; \
      ls -la /tmp || true; \
      echo "==============================================================="; \
    fi

# ------------------------------------------------------------
# BUILD-TIME TEST GATE (fail build => Railway cannot deploy)
# ------------------------------------------------------------
# - No -x: run all tests to show all failures
# - No -q: don't suppress output (Railway needs logs)
# - -ra: include summary of skipped/xfail/xpass
# - --continue-on-collection-errors: show multiple import/collection issues
RUN if [ "${RUN_TESTS}" != "0" ]; then \
      if [ "${DEBUG_MODE:-FALSE}" = "TRUE" ]; then \
        echo "================ RUNNING PYTEST (FULL DEBUG) ================"; \
        echo "🧪 ENV (filtered)"; \
        env | sort | grep -E '^(PYTHONPATH|KNOWLEDGE_CACHE_DIR|KNOWLEDGE_PERSIST_ROOT|FORCE_REBUILD_INDEX|RUN_TESTS|DEBUG_MODE)=' || true; \
        echo ""; \
      fi; \
      python -m pytest /srv/tests --disable-warnings --tb=short -ra --continue-on-collection-errors; \
    else \
      echo "⚠️ RUN_TESTS=0 → skipping build-time tests"; \
    fi

# ------------------------------------------------------------
# POST-TEST DEBUG (only runs if tests passed)
# ------------------------------------------------------------
RUN if [ "${DEBUG_MODE:-FALSE}" = "TRUE" ]; then \
      echo "================ POST-TEST DEBUG (AFTER TESTS PASSED) ================"; \
      echo "🔎 FIND knowledge_cache DIRECTORIES (may be none at build-time)"; \
      find / -type d -name knowledge_cache 2>/dev/null | head -n 200 || true; \
      echo ""; \
      echo "🔎 FIND bm25.json"; \
      find / -type f -name bm25.json 2>/dev/null | head -n 200 || true; \
      echo ""; \
      echo "🔎 FIND faiss.index"; \
      find / -type f -name faiss.index 2>/dev/null | head -n 200 || true; \
      echo "==============================================================="; \
    fi

# ------------------------------------------------------------
# Expose port
# ------------------------------------------------------------
EXPOSE 8000

# ------------------------------------------------------------
# Startup command (no crash-loop testing)
# ------------------------------------------------------------
RUN echo "🔥 DOCKERFILE REBUILT AT $(date)"

CMD ["sh", "-e", "-c", "\
  echo \"🚦 Container startup\"; \
  DEBUG_MODE=\"${DEBUG_MODE:-FALSE}\"; \
  if [ \"$DEBUG_MODE\" = \"TRUE\" ]; then \
    echo \"================ RUNTIME DEBUG (STARTUP) ================\"; \
    echo \"🧪 ENVIRONMENT VARIABLES (filtered)\"; \
    env | sort | grep -E '^(PYTHONPATH|KNOWLEDGE_CACHE_DIR|KNOWLEDGE_PERSIST_ROOT|FORCE_REBUILD_INDEX|MASTER_RESET|RUN_TESTS|DEBUG_MODE)=' || true; \
    echo \"\"; \
    echo \"📂 /data tree (runtime; Railway volume should be mounted here)\"; \
    ls -la /data || true; \
    ls -la /data/knowledge_cache || true; \
    ls -la /data/knowledge_cache/characters || true; \
    ls -la /data/knowledge_cache/characters/ || true; \
    echo \"\"; \
    echo \"📂 /srv/backend/app/knowledge/characters/ (image bundles)\"; \
    ls -la /srv/backend/app/knowledge/characters/ || true; \
    echo \"========================================================\"; \
  fi; \
  \
  if [ \"${MASTER_RESET:-0}\" = \"1\" ]; then \
    echo \"🔥🔥🔥 MASTER_RESET=1 → WIPING ALL USER DATA AND INDEXES 🔥🔥🔥\"; \
    echo \"Deleting: SQLite DB, user logs, knowledge cache, debug runs, test cases...\"; \
    rm -rf /data/* || true; \
    echo \"✅ /data completely wiped. Starting fresh.\"; \
    echo \"⚠️  MASTER_RESET forces full index rebuild regardless of FORCE_REBUILD_INDEX.\"; \
  elif [ \"${FORCE_REBUILD_INDEX:-0}\" = \"1\" ]; then \
    echo \"🔥 FORCE_REBUILD_INDEX=1 → wiping knowledge cache only\"; \
    rm -rf /data/knowledge_cache || true; \
    echo \"🧹 Knowledge cache wiped (user data preserved).\"; \
  else \
    if [ \"$DEBUG_MODE\" = \"TRUE\" ]; then echo \"ℹ️ Preserving /data (no reset flags set)\"; fi; \
  fi; \
  \
  if [ \"$DEBUG_MODE\" = \"TRUE\" ]; then echo \"🧠 Building knowledge indexes\"; fi; \
  python -m backend.app.knowledge.build.build_index; \
  \
  if [ \"$DEBUG_MODE\" = \"TRUE\" ]; then \
    echo \"================ RUNTIME DEBUG (AFTER BUILD_INDEX) ================\"; \
    echo \"📂 /data/knowledge_cache/characters/\"; \
    ls -la /data/knowledge_cache/characters/ || true; \
    echo \"🔎 Find bm25.json/faiss.index under /data\"; \
    find /data -type f -name bm25.json 2>/dev/null | head -n 50 || true; \
    find /data -type f -name faiss.index 2>/dev/null | head -n 50 || true; \
    echo \"===============================================================\"; \
  fi; \
  \
  echo \"🚀 Starting server\"; \
  exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 \
"]