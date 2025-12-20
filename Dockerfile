FROM python:3.10-slim

WORKDIR /app

ENV PYTHONPATH=/app/backend
# If you mount a Railway Volume at /data, we’ll store artifacts there:
ENV KNOWLEDGE_CACHE_DIR=/data/knowledge_cache

COPY backend/ /app/backend/

RUN pip install --no-cache-dir -r backend/requirements.txt

# Log exact versions (optional)
RUN python backend/app/knowledge/build/print_env_versions.py

EXPOSE 8000

# Ensure indexes at startup, then run uvicorn
CMD ["sh", "-c", "python -m backend.app.knowledge.runtime.ensure_cache && uvicorn app.main:app --host 0.0.0.0 --port 8000"]


CMD ["sh", "-c", "\
  if [ \"$RUN_TESTS\" != \"0\" ]; then \
    echo \"🧪 RUN_TESTS=$RUN_TESTS → running tests\" && \
    pytest tests/backend; \
  else \
    echo \"⚠️ RUN_TESTS=0 → skipping tests\"; \
  fi && \
  python -m backend.app.knowledge.runtime.ensure_cache && \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 \
"]