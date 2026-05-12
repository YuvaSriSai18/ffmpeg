# Redis Health Check Guide

## Quick Commands

### Check Redis Status
```bash
# In Docker
docker exec stt-redis redis-cli ping
# Expected output: PONG

# Check Redis info
docker exec stt-redis redis-cli info

# Check connected clients
docker exec stt-redis redis-cli client list

# Check memory usage
docker exec stt-redis redis-cli info memory
```

### Check All Services

```bash
# View all running containers
docker compose -f docker-compose-single.yml ps

# View logs for all services
docker compose -f docker-compose-single.yml logs -f

# View logs for specific service
docker compose -f docker-compose-single.yml logs -f stt-app
docker compose -f docker-compose-single.yml logs -f stt-redis

# Get container stats (CPU, memory, network)
docker stats
```

### Check Port Usage

**Linux/Mac:**
```bash
# See which process is using a port
lsof -i :6379    # Redis
lsof -i :8000    # API Gateway
lsof -i :8001    # Audio Processor
lsof -i :8002    # Transcriber

# Kill process using port
sudo fuser -k 6379/tcp
```

**Windows (PowerShell):**
```powershell
# Check port usage
netstat -ano | findstr :6379
netstat -ano | findstr :8000

# Kill process
taskkill /PID <PID> /F
```

## Troubleshooting Port Conflicts

### If Redis port is already in use:

**Option 1: Use different port**
```bash
# Edit .env
REDIS_PORT=6380

# Restart
docker compose -f docker-compose-single.yml down
docker compose -f docker-compose-single.yml up -d
```

**Option 2: Kill process using the port**
```bash
# Linux/Mac
sudo fuser -k 6379/tcp

# Windows
netstat -ano | findstr :6379
taskkill /PID <PID> /F

# Restart containers
docker compose -f docker-compose-single.yml restart
```

## Environment Variables

### User Configuration

Users who pull your image should create a `.env` file:

```bash
# Copy template
cp .env.example .env

# Edit for their environment
nano .env
```

### Docker Compose Reads .env Automatically

When you run `docker compose`, it automatically reads `.env` in the current directory:

```bash
docker compose -f docker-compose-single.yml up -d
```

Variables are loaded in this order (highest priority last):
1. Defaults in docker-compose.yml
2. `.env` file in current directory
3. Command-line `-e` flags

### Example Custom Configuration

```bash
# .env for high-traffic deployment
REDIS_PORT=6379
API_PORT=8000
AUDIO_PORT=8001
TRANSCRIBER_PORT=8002
ENVIRONMENT=production
LOG_LEVEL=WARNING
WORKER_CONCURRENCY=8
STREAMING_WORKERS=4
WHISPER_MODEL=large
MAX_FILE_SIZE=500
```

## Testing Redis Connectivity

```bash
# From inside the app container
docker exec stt-app python -c "
import redis
r = redis.Redis(host='redis', port=6379, decode_responses=True)
print('Redis connected:', r.ping())
"

# Via Redis CLI
docker exec stt-redis redis-cli PING
docker exec stt-redis redis-cli DBSIZE
docker exec stt-redis redis-cli KEYS '*'
```

## GitHub Actions Debugging

### View Workflow Logs

1. Go to your repository
2. Click "Actions" tab
3. Select the failed workflow
4. Click the job to see detailed logs

### Common Issues in CI/CD

**Port already allocated:**
- Fixed with improved cleanup script
- Kills processes on ports 6379, 8000, 8001, 8002 before starting

**Container won't start:**
- Check logs: `docker compose logs stt-app`
- Verify .env variables are correct
- Ensure no port conflicts

**Redis connection timeout:**
- Increase health check timeout in docker-compose
- Check Redis container is healthy: `docker compose ps`
