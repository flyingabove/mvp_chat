FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy backend folder into container
COPY backend/ /app/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Log exact versions into Railway deploy logs
RUN python backend/app/knowledge/build/print_env_versions.py

# Install Faiss
RUN python backend/app/knowledge/build/build_index.py

# Expose port (Railway maps this automatically)
EXPOSE 8000

# Start FastAPI using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
