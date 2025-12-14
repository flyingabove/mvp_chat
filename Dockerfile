FROM python:3.10-slim

WORKDIR /app

# Copy backend into /app/backend
COPY backend/ /app/backend/

# Install dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

# Log exact versions
RUN python backend/app/knowledge/build/print_env_versions.py

# Build FAISS + BM25 indexes
RUN python -m backend.app.knowledge.build.build_index

# Expose port (Railway maps this automatically)
EXPOSE 8000

ENV PYTHONPATH=/app/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

