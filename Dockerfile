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
# Copy code
# ------------------------------------------------------------
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
# Startup command
# ------------------------------------------------------------
CMD ["sh", "-e", "-c", "\
  if [ \"${RUN_TESTS:-1}\" != \"0\" ]; then \
    echo \"🧪 RUN_TESTS=${RUN_TESTS:-1} → running tests\"; \
    python -m pytest /app/tests; \
    echo \"✅ Tests passed\"; \
  else \
    echo \"⚠️ RUN_TESTS=0 → skipping tests\"; \
  fi; \
  \
  echo \"🧠 Ensuring knowledge indexes (FORCE_REBUILD_INDEX=${FORCE_REBUILD_INDEX:-0})\"; \
  python -m backend.app.knowledge.build.ensure_indexes; \
  \
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
"]

