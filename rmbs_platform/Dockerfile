FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for ML libraries (scipy, scikit-learn)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories (ephemeral, but needed at startup)
RUN mkdir -p deals collateral performance scenarios results \
    deals_versions collateral_versions performance_versions scenarios_versions

# Cloud Run expects PORT env var, default 8080
ENV PORT=8080
ENV RMBS_API_HOST=0.0.0.0
ENV RMBS_API_PORT=8080
ENV RMBS_LOG_LEVEL=INFO
ENV RMBS_ENABLE_CORS=true

# Run uvicorn - Cloud Run sets PORT automatically
ENV PYTHONPATH=/app
CMD exec uvicorn api_main:app --host 0.0.0.0 --port ${PORT}
