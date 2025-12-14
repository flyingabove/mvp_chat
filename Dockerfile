FROM python:3.10-slim

WORKDIR /app

# Make backend importable everywhere
ENV PYTHONPATH=/app/backend

# Copy backend into container
COPY backend/ /app/backend/

# Install dependencies (includes torch CPU via find-links)
RUN pip install --no-cache-dir -r backend/requirements.txt

# Log exact versions into Railway logs
RUN python backend/app/knowledge/build/print_env_versions.py

# Build FAISS + BM25 indexes (module mode)
RUN python -m backend.app.knowledge.build.build_index

# Expose port (Railway maps this automatically)
EXPOSE 8000

# Start FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
