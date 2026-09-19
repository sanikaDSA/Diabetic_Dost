# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install system dependencies (audio processing codecs, curl for healthchecks, build essentials)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU wheels and project Python requirements
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy all project files
COPY . /app/

# Create runtime directories for persistent outputs and datasets
RUN mkdir -p \
    /app/outputs/database \
    /app/outputs/reports/sessions \
    /app/outputs/logs \
    /app/outputs/checkpoints \
    /app/datasets/raw_audio \
    /app/datasets/processed_audio \
    /app/datasets/transcripts \
    /app/datasets/manifests \
    /app/datasets/reviewed

# Set working directory to backend application
WORKDIR /app/backend

# Expose application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Start FastAPI server
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
