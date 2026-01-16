# Speech-to-Text (STT) Transcription Service

A production-ready microservices-based speech-to-text transcription system using OpenAI Whisper, FastAPI, Redis, and FFmpeg.

## 🚀 Features

- **RESTful API** - Simple HTTP endpoints for audio upload and transcription
- **Asynchronous Processing** - Jobs queued via Redis for scalable processing
- **Multiple Audio Formats** - Supports WAV, MP3, M4A, FLAC, OGG, WebM
- **FFmpeg Docker Integration** - Audio conversion in containerized environment
- **OpenAI Whisper Base Model** - Accurate speech recognition via Python package
- **Microservices Architecture** - Independent, scalable Docker containers
- **Production Ready** - Structured logging, health checks, error handling

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [API Documentation](#api-documentation)
- [Configuration](#configuration)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│ API Gateway │ ───> │    Redis     │ ───> │   Audio     │
│  (FastAPI)  │      │   (Queue)    │      │  Processor  │
└─────────────┘      └──────────────┘      └─────────────┘
                              │                     │
                              │                     ▼
                              │             ┌─────────────┐
                              └──────────>  │ Transcriber │
                                           │  (Whisper)  │
                                           └─────────────┘
```

### Components

1. **API Gateway** (`api-gateway/`) - HTTP API for file upload and job status
2. **Audio Processor** (`audio-processor/`) - Audio format conversion and preprocessing
3. **Transcriber** (`transcriber/`) - Speech-to-text using OpenAI Whisper
4. **Redis** - Message queue and job metadata storage
5. **Shared** (`shared/`) - Common models, Redis client, logging configuration

## ⚡ Quick Start

### Prerequisites

- Docker and Docker Compose
- Sample audio file (MP3/WAV)

### 1. Start All Services

```bash
docker-compose up -d --build
```

This starts:
- Redis (message queue)
- API Gateway (port 8000)
- Audio Processor (with FFmpeg)
- Transcriber (with Whisper base model)

### 2. Wait for Services

```bash
# Check services are running
docker-compose ps

# View logs
docker-compose logs -f
```

Wait ~30 seconds for Whisper model to download on first run.

### 3. Test the API

**Interactive Docs:**
Visit **http://localhost:8000/docs**

**Upload Audio:**
```bash
curl -X POST "http://localhost:8000/v1/stt/jobs" \
     -F "file=@audio/sample_audio.mp3"
```

**Run Test Script:**
```bash
python test_endpoints_simple.py
```

### 4. Stop Services

```bash
docker-compose down
```

## 📦 Requirements

### Docker (Recommended)

All dependencies are included in Docker images:
- FFmpeg (in audio-processor container)
- OpenAI Whisper (in transcriber container)
- Redis (standalone container)
- Python packages (all containers)

**Install Docker:**
- **Linux:** `sudo apt-get install docker.io docker-compose`
- **macOS:** Download Docker Desktop
- **Windows:** Download Docker Desktop

### Python Testing (Optional)

To run test scripts locally:
```bash
pip install requests
```

## 📖 API Documentation

### Base URL
```
http://localhost:8000
```

### Endpoints

#### 1. Health Check
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "api-gateway",
  "timestamp": "2026-01-13T12:00:00.000000"
}
```

#### 2. Upload Audio File (Create Job)
```http
POST /v1/stt/jobs
Content-Type: multipart/form-data
```

**Parameters:**
- `file` (required) - Audio file (WAV, MP3, M4A, FLAC, OGG, WebM)

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status_url": "/v1/stt/jobs/550e8400-e29b-41d4-a716-446655440000"
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/v1/stt/jobs" \
     -F "file=@/path/to/audio.mp3"
```

#### 3. Get Job Status and Results
```http
GET /v1/stt/jobs/{job_id}
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "metadata": {
    "original_filename": "audio.mp3",
    "file_size": 1048576,
    "content_type": "audio/mpeg",
    "uploaded_at": "2026-01-13T12:00:00.000000"
  },
  "result": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "text": "This is the transcribed text from the audio file.",
    "language": "en",
    "duration": 45.6,
    "transcribed_at": "2026-01-13T12:01:00.000000",
    "segments": [
      {
        "start": 0.0,
        "end": 5.2,
        "text": "This is the transcribed text"
      }
    ]
  }
}
```

**Job Status Values:**
- `uploaded` - File received, queued for processing
- `processing` - Audio being converted
- `transcribing` - Speech recognition in progress
- `completed` - Transcription finished successfully
- `failed` - Processing failed (check logs)

#### 4. Root Endpoint
```http
GET /
```

Returns API information and available endpoints.

### Error Responses

**400 Bad Request:**
```json
{
  "detail": "File type .xyz not allowed. Allowed: {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.webm'}"
}
```

**404 Not Found:**
```json
{
  "detail": "Job 550e8400-e29b-41d4-a716-446655440000 not found"
}
```

**413 Payload Too Large:**
```json
{
  "detail": "File too large. Max 100MB"
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Failed to process upload: [error message]"
}
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Redis Configuration
REDIS_URL=redis://localhost:6379

# Data Storage
DATA_DIR=./data

# API Gateway
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=INFO
MAX_FILE_SIZE=100

# Audio Processor
WORKER_CONCURRENCY=2

# Transcriber
WHISPER_MODEL=base
```

### Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379` | Redis connection URL |
| `DATA_DIR` | `/data` | Directory for files in container |
| `PORT` | `8000` | API Gateway port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MAX_FILE_SIZE` | `100` | Max upload size in MB |
| `WORKER_CONCURRENCY` | `2` | Concurrent audio processing jobs |
| `WHISPER_MODEL` | `base` | Whisper model (tiny/base/small/medium/large) |

### Whisper Models

| Model | Size | Accuracy | Speed |
|-------|------|----------|-------|
| tiny | ~75MB | ⭐⭐ | ⚡⚡⚡⚡⚡ |
| base | ~150MB | ⭐⭐⭐ | ⚡⚡⚡⚡ |
| small | ~500MB | ⭐⭐⭐⭐ | ⚡⚡⚡ |
| medium | ~1.5GB | ⭐⭐⭐⭐⭐ | ⚡⚡ |
| large | ~3GB | ⭐⭐⭐⭐⭐ | ⚡ |

**Recommendation:** Use `base` for development, `small` or `medium` for production.

## 🔧 Development

### Project Structure

```
.
├── api-gateway/           # FastAPI HTTP API
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── audio-processor/       # FFmpeg audio conversion
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── transcriber/           # Whisper transcription
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── shared/                # Shared modules
│   ├── models.py          # Data models
│   ├── redis_client.py    # Redis client
│   └── logging_config.py  # Logging setup
├── data/                  # Runtime data
│   ├── uploads/           # Uploaded files
│   └── processed/         # Converted files
├── audio/                 # Sample audio files
├── docker-compose.yml     # Container orchestration
├── .env                   # Configuration
└── test_endpoints_simple.py # API test script
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api-gateway
docker-compose logs -f audio-processor
docker-compose logs -f transcriber
```

### Rebuild After Code Changes

```bash
docker-compose down
docker-compose up -d --build
```bash
docker-compose up -d --build
```

### Stop Services

```bash
docker-compose down
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api-gateway
docker-compose logs -f audio-processor
docker-compose logs -f transcriber
```

### Scale Services

```bash
# Scale audio processors
docker-compose up -d --scale audio-processor=3

# Scale transcribers
docker-compose up -d --scale transcriber=2
```

## 🧪 Testing

### Test Script

**Python:**
```bash
python test_endpoints_simple.py
```

This will:
1. Check health endpoint
2. Upload sample audio
3. Poll for completion
4. Display transcription results

### Manual Testing with curl

```bash
# 1. Upload audio
RESPONSE=$(curl -s -X POST "http://localhost:8000/v1/stt/jobs" \
     -F "file=@audio/sample_audio.mp3")
JOB_ID=$(echo $RESPONSE | grep -o '"job_id":"[^"]*' | cut -d'"' -f4)

echo "Job ID: $JOB_ID"

# 2. Check status
curl "http://localhost:8000/v1/stt/jobs/$JOB_ID"
```

### Using Swagger UI

1. Open http://localhost:8000/docs
2. Click on "POST /v1/stt/jobs"
3. Click "Try it out"
4. Upload an audio file
5. Execute
6. Copy the `job_id` from response
7. Use "GET /v1/stt/jobs/{job_id}" to check status

## 🐛 Troubleshooting

### Redis Connection Errors

**Error:** `ConnectionError: Error connecting to localhost:6379`

**Solution:**
```bash
# Check if Redis is running
docker ps | grep redis

# Start Redis
docker run -d -p 6379:6379 --name stt-redis redis:7

# Test connection
redis-cli ping  # Should return "PONG"
```

### FFmpeg Not Found

**Error:** `FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'`

**Solution:**

Linux:
```bash
sudo apt-get install ffmpeg
```

macOS:
```bash
brew install ffmpeg
```

Windows: Download from https://ffmpeg.org/download.html and add to PATH

### Whisper Model Download Issues

**Error:** `PermissionError: [Errno 13] Permission denied: '/.cache/whisper'`

**Solution:** This typically happens in Docker. The Dockerfile already fixes this by setting proper permissions. If running locally, ensure your user has write access to the cache directory:

```bash
mkdir -p ~/.cache/whisper
chmod 755 ~/.cache/whisper
```

### Port Already in Use

**Error:** `OSError: [Errno 98] Address already in use`

**Solution:**

Linux/macOS:
```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>
```

Windows:
```cmd
# Find process
netstat -ano | findstr :8000

# Kill process
taskkill /PID <PID> /F
```

### Large Files Failing

**Error:** `File too large. Max 100MB`

**Solution:** Increase `MAX_FILE_SIZE` in `.env`:
```env
MAX_FILE_SIZE=500  # 500MB
```

### Slow Transcription

**Issue:** Transcription takes too long

**Solutions:**
1. Use smaller Whisper model: `WHISPER_MODEL=tiny`
2. Use GPU acceleration (requires CUDA-enabled PyTorch)
3. Scale transcriber services: `docker-compose up -d --scale transcriber=3`

## 📊 Performance

### Benchmarks (base model, CPU)

| Audio Length | Processing Time | Model |
|--------------|----------------|-------|
| 30 seconds | ~5-10 seconds | base |
| 2 minutes | ~15-30 seconds | base |
| 10 minutes | ~1-2 minutes | base |

*Performance varies based on CPU/GPU, audio quality, and model size.*

### Resource Requirements

| Component | CPU | Memory | Disk |
|-----------|-----|--------|------|
| API Gateway | Low | 100MB | Minimal |
| Audio Processor | Medium | 200MB | Temporary |
| Transcriber (base) | High | 2GB | 500MB (model cache) |
| Redis | Low | 100MB | Variable |

## 📝 License

MIT License - See LICENSE file for details

## 🔄 Changelog

### Version 1.0.0 (2026-01-13)
- Initial release
- OpenAI Whisper integration
- Microservices architecture
- Docker support
- RESTful API
- Multiple audio format support
- Asynchronous job processing
