# Production Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./

# Create the runtime user. The container starts as root only so the entrypoint
# can take ownership of the mounted data volume, then it drops to appuser.
RUN useradd -m appuser \
    && chown -R appuser:appuser /app \
    && chmod +x /app/docker-entrypoint.sh

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DATA_DIR=/app/data

# Hosting platforms inject PORT; 8000 keeps `docker run -p 8000:8000` working.
ENV PORT=8000
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]