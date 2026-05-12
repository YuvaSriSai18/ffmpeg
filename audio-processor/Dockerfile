FROM python:3.11-slim

WORKDIR /app

# Install FFmpeg and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    build-essential \
    python3-dev \
    python3-setuptools \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip, setuptools, and wheel
RUN pip install --no-cache-dir --upgrade pip wheel

# Verify FFmpeg installation
RUN ffmpeg -version

# Copy requirements
COPY audio-processor/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY audio-processor/main.py .
COPY shared /app/shared

# Create data directories
RUN mkdir -p /data/uploads /data/processed

EXPOSE 8001

CMD ["python", "main.py"]
