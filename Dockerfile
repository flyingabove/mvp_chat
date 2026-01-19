FROM python:3.10-slim

# ------------------------------------------------------------
# GLOBAL ENV -- match prod as closely as possible
# ------------------------------------------------------------
ENV PYTHONPATH=/srv
ENV KNOWLEDGE_CACHE_DIR=/data/knowledge_cache
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ------------------------------------------------------------
# Reset filesystem to remove any doubt
# ------------------------------------------------------------
RUN echo "🔥 RESETTING FILESYSTEM" \
 && rm -rf /srv /tmp /data \
 && mkdir -p /srv /tmp /data \
 && chmod 1777 /tmp

WORKDIR /srv

# ------------------------------------------------------------
# Copy application + tests
# ------------------------------------------------------------
COPY backend/ /srv/backend/
COPY tests/ /srv/tests/

# ------------------------------------------------------------
# Install dependencies
# ------------------------------------------------------------
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt

# ------------------------------------------------------------
# 🔍 DEBUG: ENV + FILESYSTEM BEFORE TESTS
# ------------------------------------------------------------
RUN echo "================ BUILD-TIME DEBUG (BEFORE TESTS) ================" \
 && echo "🧪 ENVIRONMENT VARIABLES" \
 && env | sort \
 && echo "" \
 && echo "📂 /data tree (before tests)" \
 && ls -R /data || true \
 && echo "" \
 && echo "📂 /tmp tree (before tests)" \
 && ls -R /tmp || true \
 && echo "" \
 && echo "📂 /srv/backend/app/knowledge" \
 && ls -R /srv/backend/app/knowledge || true \
 && echo "==============================================================="

# ------------------------------------------------------------
# 🧪 RUN PYTEST -- DO NOT STOP ON FAILURE
# ------------------------------------------------------------
RUN echo "================ RUNNING PYTEST (FULL DEBUG) ================" \
 && python -m pytest -q --disable-warnings --tb=short -ra /srv/tests || true \
 && echo "================ PYTEST FINISHED ================"

# ------------------------------------------------------------
# 🔍 DEBUG: FILESYSTEM AFTER TESTS
# ------------------------------------------------------------
RUN echo "================ POST-TEST FILESYSTEM DEBUG ================" \
 && echo "📂 /data tree (after tests)" \
 && ls -R /data || true \
 && echo "" \
 && echo "📂 /tmp tree (after tests)" \
 && ls -R /tmp || true \
 && echo "" \
 && echo "🔎 FIND ALL knowledge_cache DIRECTORIES" \
 && find / -type d -name knowledge_cache 2>/dev/null || true \
 && echo "" \
 && echo "🔎 FIND bm25.json" \
 && find / -type f -name bm25.json 2>/dev/null || true \
 && echo "" \
 && echo "🔎 FIND faiss.index" \
 && find / -type f -name faiss.index 2>/dev/null || true \
 && echo "==============================================================="

# ------------------------------------------------------------
# Keep container alive so Railway shows logs clearly
# ------------------------------------------------------------
CMD ["bash"]
