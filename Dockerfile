# Storyteller-V2 API Backend
FROM python:3.11-slim AS backend

WORKDIR /app

# Install system dependencies for sentence-transformers and PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

# Copy application code
COPY backend/ backend/
COPY shared/ shared/
COPY ingestion/ ingestion/
COPY storyteller/ storyteller/

# Create data directories
RUN mkdir -p data/static data/lore data/style

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
