FROM python:3.10-slim

# ------------------------------------------------------------
# App setup
# ------------------------------------------------------------
ENV PYTHONPATH=/srv
ENV KNOWLEDGE_CACHE_DIR=/data/knowledge_cache
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

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

# ------------------------------------------------------------
# Install dependencies
# ------------------------------------------------------------
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt

# Optional: log environment versions (safe, fast)
RUN python /srv/backend/app/knowledge/build/print_env_versions.py

# ------------------------------------------------------------
# BUILD-TIME TEST GATE (fail build => Railway cannot deploy)
# ------------------------------------------------------------
RUN if [ "${RUN_TESTS}" != "0" ]; then \
      echo "🧪 Running tests at build time (fail stops deploy)"; \
      python -m pytest -x -q --disable-warnings /srv/tests; \
    else \
      echo "⚠️ RUN_TESTS=0 → skipping build-time tests"; \
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
  echo \"🚀 Starting server\"; \
  exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 \
"]
