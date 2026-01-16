FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (ffmpeg for audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY transcriber/requirements.txt .

# Install Python dependencies (includes openai-whisper)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY transcriber/main.py .
COPY shared /app/shared

# Create cache directory for Whisper models
RUN mkdir -p /root/.cache/whisper /data && \
    chmod -R 755 /root/.cache/whisper

EXPOSE 8002

CMD ["python", "main.py"]
