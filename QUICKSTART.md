# 🚀 Quick Start Guide

## Start Services
```bash
docker-compose up -d --build
```

Wait ~30 seconds for Whisper model download on first run.

## Test API

### Health Check
```bash
curl http://localhost:8000/health
```

### Upload Audio
```bash
curl -X POST "http://localhost:8000/v1/stt/jobs" -F "file=@audio/sample_audio.mp3"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status_url": "/v1/stt/jobs/550e8400-e29b-41d4-a716-446655440000"
}
```

### Check Job Status
```bash
curl http://localhost:8000/v1/stt/jobs/550e8400-e29b-41d4-a716-446655440000
```

## View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f transcriber
```

## Interactive API Docs
**http://localhost:8000/docs**

## Stop Services
```bash
docker-compose down
```

## Run Test Script
```bash
python test_endpoints_simple.py
```

## Full Documentation
See [README.md](README.md) for complete API reference and configuration.


### Redis Not Running
```cmd
docker run -d -p 6379:6379 --name stt-redis redis:7
```

### Module Not Found
```cmd
pip install fastapi uvicorn redis pydantic python-multipart aiofiles openai-whisper
```

## ✨ Features Working

- ✅ Health check endpoint
- ✅ File upload (WAV, MP3, M4A, FLAC, OGG, WebM)
- ✅ Job creation and tracking
- ✅ Redis queue integration
- ✅ Async processing
- ✅ Structured logging
- ⏳ Audio conversion (needs audio-processor running)
- ⏳ Speech transcription (needs transcriber running)

Start the other services to enable full transcription!
