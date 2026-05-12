# Setup Instructions

## Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/ffmpeg.git
cd ffmpeg
```

### 2. Configure Environment Variables

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` to customize settings (optional - defaults are provided):

```bash
# Redis Configuration
REDIS_PORT=6379              # Default: 6379 (change if port is already in use)

# API Ports
API_PORT=8000                # API Gateway port
AUDIO_PORT=8001              # Audio Processor port
TRANSCRIBER_PORT=8002        # Transcriber port

# Application Settings
ENVIRONMENT=development      # development or production
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR, CRITICAL
WORKER_CONCURRENCY=2        # Number of worker processes
WHISPER_MODEL=base          # tiny, base, small, medium, large
MAX_FILE_SIZE=100           # Maximum upload size in MB
```

### 3. Run with Docker Compose

**Option A: Using the consolidated single image (recommended)**
```bash
docker compose -f docker-compose-single.yml up -d
```

**Option B: Using separate services**
```bash
docker compose up -d
```

### 4. Verify Services

```bash
# Check running containers
docker compose -f docker-compose-single.yml ps

# Check Redis connection
docker exec stt-redis redis-cli ping
# Expected: PONG

# Check API Gateway
curl http://localhost:8000/health
```

### 5. Access Services

- **API Gateway**: http://localhost:8000
- **Audio Processor**: http://localhost:8001
- **Transcriber**: http://localhost:8002
- **Redis CLI**: `docker exec -it stt-redis redis-cli`

## Troubleshooting

### Port Already in Use

If you get "port is already allocated" error:

```bash
# Linux/Mac - Kill process using port
sudo fuser -k 6379/tcp    # Redis
sudo fuser -k 8000/tcp    # API Gateway
sudo fuser -k 8001/tcp    # Audio Processor
sudo fuser -k 8002/tcp    # Transcriber

# Windows
netstat -ano | findstr :6379
taskkill /PID <PID> /F
```

Or change ports in `.env`:
```bash
REDIS_PORT=6380
API_PORT=8010
AUDIO_PORT=8011
TRANSCRIBER_PORT=8012
```

### Container Won't Start

```bash
# View logs
docker compose -f docker-compose-single.yml logs -f stt-app

# Rebuild image
docker compose -f docker-compose-single.yml build --no-cache

# Full restart
docker compose -f docker-compose-single.yml down -v
docker compose -f docker-compose-single.yml up -d
```

### Redis Connection Issues

```bash
# Check Redis is running
docker compose -f docker-compose-single.yml ps redis

# Check Redis logs
docker compose -f docker-compose-single.yml logs redis

# Test connection manually
docker exec -it stt-redis redis-cli PING
```

## Pushing to Docker Hub

### Prerequisites
1. Create Docker Hub account: https://hub.docker.com
2. Create Personal Access Token in [Security Settings](https://hub.docker.com/settings/security)
3. Login locally:
   ```bash
   docker login
   # Enter username and PAT
   ```

### Build and Push

```bash
# Build image
docker build -t yourusername/ffmpeg-stt-app:latest .

# Push to Docker Hub
docker push yourusername/ffmpeg-stt-app:latest
```

### Pull and Run from Docker Hub

```bash
# Pull image
docker pull yourusername/ffmpeg-stt-app:latest

# Create .env file with your settings
cp .env.example .env

# Run
docker compose -f docker-compose-single.yml up -d
```

## Development

### Running Tests

```bash
# Run all tests
python test_endpoints_simple.py
python test_streaming_asr.py
python test_websocket_streaming.py
```

### Building Locally

```bash
# Build without cache (fresh build)
docker compose -f docker-compose-single.yml build --no-cache

# Rebuild specific service
docker compose -f docker-compose-single.yml build --no-cache stt-app
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379` | Redis connection string |
| `REDIS_PORT` | `6379` | Redis port binding |
| `DATA_DIR` | `./data` | Audio files storage |
| `API_PORT` | `8000` | API Gateway port |
| `AUDIO_PORT` | `8001` | Audio Processor port |
| `TRANSCRIBER_PORT` | `8002` | Transcriber port |
| `ENVIRONMENT` | `development` | App environment |
| `LOG_LEVEL` | `INFO` | Logging level |
| `WORKER_CONCURRENCY` | `2` | Number of workers |
| `STREAMING_WORKERS` | `1` | WebSocket workers |
| `WHISPER_MODEL` | `base` | Whisper model size |
| `MAX_FILE_SIZE` | `100` | Max upload size (MB) |

## GitHub Actions CI/CD

The repository includes automated workflows:

1. **Tests** (`tests.yml`) - Runs on PR and push
   - Linting checks
   - Docker build verification
   - Integration tests

2. **Docker Build & Push** (`docker-build-push.yml`) - Runs on success
   - Builds Docker image
   - Pushes to Docker Hub
   - Auto-tags (main = latest, branches = branch-name)

### Setup GitHub Actions Secrets

1. Go to: Repository → Settings → Secrets and variables → Actions
2. Add secrets:
   - `DOCKER_HUB_USERNAME` - Your Docker Hub username
   - `DOCKER_HUB_PASSWORD` - Your Personal Access Token (NOT password)

Tests must pass before pushing to Docker Hub!
