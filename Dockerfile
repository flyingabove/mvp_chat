FROM python:3.10-slim

# ------------------------------------------------------------
# App setup
# ------------------------------------------------------------
WORKDIR /app

ENV PYTHONPATH=/app/backend
ENV KNOWLEDGE_CACHE_DIR=/data/knowledge_cache
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ------------------------------------------------------------
# Copy code (clean, deterministic)
# ------------------------------------------------------------
RUN echo "🔥 Cleaning /app before copy"
RUN rm -rf /app

COPY backend/ /app/backend/
COPY tests/ /app/tests/

# ------------------------------------------------------------
# Install dependencies
# ------------------------------------------------------------
RUN pip install --no-cache-dir -r backend/requirements.txt

# Optional: log environment versions (safe, fast)
RUN python backend/app/knowledge/build/print_env_versions.py

# ------------------------------------------------------------
# Expose port
# ------------------------------------------------------------
EXPOSE 8000

# ------------------------------------------------------------
# Startup command (correct order, correct module)
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
  python -m app.knowledge.build.build_index; \
  \
  if [ \"${RUN_TESTS:-1}\" != \"0\" ]; then \
    echo \"🧪 RUN_TESTS=${RUN_TESTS:-1} → running tests\"; \
    python -m pytest /app/tests; \
    echo \"✅ Tests passed\"; \
  else \
    echo \"⚠️ RUN_TESTS=0 → skipping tests\"; \
  fi; \
  \
  echo \"🚀 Starting server\"; \
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
"]

