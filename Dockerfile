FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    build-essential \
    python3-dev \
    python3-setuptools \
    git \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip, setuptools, and wheel
RUN pip install --no-cache-dir --upgrade pip wheel

# Install all requirements combined
COPY transcriber/requirements.txt ./requirements-transcriber.txt
COPY audio-processor/requirements.txt ./requirements-audio.txt
COPY api-gateway/requirements.txt ./requirements-api.txt

RUN pip install --no-cache-dir -r requirements-transcriber.txt && \
    pip install --no-cache-dir -r requirements-audio.txt && \
    pip install --no-cache-dir -r requirements-api.txt

# Copy all application code
COPY api-gateway/main.py ./api_gateway_main.py
COPY audio-processor/main.py ./audio_processor_main.py
COPY transcriber/main.py ./transcriber_main.py
COPY shared /app/shared

# Create directories
RUN mkdir -p /root/.cache/whisper /data/uploads /data/processed && \
    chmod -R 755 /root/.cache/whisper

# Copy supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports
EXPOSE 8000 8001 8002

# Entrypoint
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
