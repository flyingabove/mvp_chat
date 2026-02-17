FROM python:3.10-slim

# ------------------------------------------------------------
# App setup
# ------------------------------------------------------------
ENV PYTHONPATH=/srv
ENV KNOWLEDGE_CACHE_DIR=/data/knowledge_cache
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Build-time secrets — Railway passes these as build args
ARG OPENAI_API_KEY=""
ENV OPENAI_API_KEY=${OPENAI_API_KEY}

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
RUN echo "================ BUILD-TIME DEBUG (BEFORE TESTS) ================" \
 && echo "🧪 ENVIRONMENT VARIABLES (filtered)" \
 && env | sort | grep -E '^(PYTHONPATH|KNOWLEDGE_CACHE_DIR|KNOWLEDGE_PERSIST_ROOT|FORCE_REBUILD_INDEX|RUN_TESTS)=' || true \
 && echo "" \
 && echo "🐍 Python / Pip" \
 && python -V \
 && pip -V \
 && echo "" \
 && echo "📦 Installed packages (top)" \
 && pip list | head -n 80 || true \
 && echo "" \
 && echo "📂 /data tree (build-time; note Railway volume mounts at runtime)" \
 && ls -la /data || true \
 && ls -la /data/knowledge_cache || true \
 && ls -la /data/knowledge_cache/characters || true \
 && ls -la /data/knowledge_cache/characters/ || true \
 && echo "" \
 && echo "📂 /srv/backend/app/knowledge/characters/ (image bundles)" \
 && ls -la /srv/backend/app/knowledge/characters/ || true \
 && echo "" \
 && echo "📂 /tmp tree (build-time)" \
 && ls -la /tmp || true \
 && echo "==============================================================="

# ------------------------------------------------------------
# BUILD-TIME TEST GATE (fail build => Railway cannot deploy)
# ------------------------------------------------------------
# - No -x: run all tests to show all failures
# - No -q: don't suppress output (Railway needs logs)
# - -ra: include summary of skipped/xfail/xpass
# - --continue-on-collection-errors: show multiple import/collection issues
RUN if [ "${RUN_TESTS}" != "0" ]; then \
      echo "================ RUNNING PYTEST (FULL DEBUG) ================"; \
      echo "🧪 ENV (filtered)"; \
      env | sort | grep -E '^(PYTHONPATH|KNOWLEDGE_CACHE_DIR|KNOWLEDGE_PERSIST_ROOT|FORCE_REBUILD_INDEX|RUN_TESTS)=' || true; \
      echo ""; \
      python -m pytest /srv/tests --disable-warnings --tb=short -ra --continue-on-collection-errors; \
    else \
      echo "⚠️ RUN_TESTS=0 → skipping build-time tests"; \
    fi

# ------------------------------------------------------------
# POST-TEST DEBUG (only runs if tests passed)
# ------------------------------------------------------------
RUN echo "================ POST-TEST DEBUG (AFTER TESTS PASSED) ================" \
 && echo "🔎 FIND knowledge_cache DIRECTORIES (may be none at build-time)" \
 && find / -type d -name knowledge_cache 2>/dev/null | head -n 200 || true \
 && echo "" \
 && echo "🔎 FIND bm25.json" \
 && find / -type f -name bm25.json 2>/dev/null | head -n 200 || true \
 && echo "" \
 && echo "🔎 FIND faiss.index" \
 && find / -type f -name faiss.index 2>/dev/null | head -n 200 || true \
 && echo "==============================================================="

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
  echo \"================ RUNTIME DEBUG (STARTUP) ================\"; \
  echo \"🧪 ENVIRONMENT VARIABLES (filtered)\"; \
  env | sort | grep -E '^(PYTHONPATH|KNOWLEDGE_CACHE_DIR|KNOWLEDGE_PERSIST_ROOT|FORCE_REBUILD_INDEX|RUN_TESTS)=' || true; \
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
  \
  if [ \"${FORCE_REBUILD_INDEX:-0}\" = \"1\" ]; then \
    echo \"🔥 FORCE_REBUILD_INDEX=1 → wiping /data\"; \
    rm -rf /data/* || true; \
    echo \"🧹 /data wiped\"; \
  else \
    echo \"ℹ️ FORCE_REBUILD_INDEX=0 → preserving /data\"; \
  fi; \
  \
  echo \"🧠 Building knowledge indexes (FORCE_REBUILD_INDEX=${FORCE_REBUILD_INDEX:-0})\"; \
  python -m backend.app.knowledge.build.build_index; \
  \
  echo \"================ RUNTIME DEBUG (AFTER BUILD_INDEX) ================\"; \
  echo \"📂 /data/knowledge_cache/characters/\"; \
  ls -la /data/knowledge_cache/characters/ || true; \
  echo \"🔎 Find bm25.json/faiss.index under /data\"; \
  find /data -type f -name bm25.json 2>/dev/null | head -n 50 || true; \
  find /data -type f -name faiss.index 2>/dev/null | head -n 50 || true; \
  echo \"===============================================================\"; \
  \
  echo \"🚀 Starting server\"; \
  exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 \
"]