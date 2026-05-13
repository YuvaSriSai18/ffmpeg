# Test Suite

Complete test suite for the FFmpeg Speech-to-Text API.

## Test Files

### 1. `test_endpoints_simple.py`
Simple Python test script for all API endpoints.

**What it tests:**
- Health check endpoint
- Root endpoint (API info)
- Audio file upload
- Job status checking
- Transcription results

**Run:**
```bash
python tests/test_endpoints_simple.py
```

**Environment variables:**
```bash
AUDIO_FILE=audio/sample_audio.mp3  # Local or URL
```

**Example with cloud audio:**
```bash
AUDIO_FILE=https://example.com/audio.mp3 python tests/test_endpoints_simple.py
```

---

### 2. `test_streaming_asr.py`
Comprehensive streaming ASR pipeline tests using pytest.

**What it tests:**
- Voice Activity Detection (VAD)
- Audio rolling buffer with backpressure
- FFmpeg streaming pipeline
- Sliding-window Whisper inference
- Latency metrics collection
- Redis session state management
- End-to-end streaming transcription

**Requirements:**
```bash
pip install pytest pytest-asyncio numpy
```

**Run:**
```bash
pytest tests/test_streaming_asr.py -v
```

**Run specific test:**
```bash
pytest tests/test_streaming_asr.py::test_vad_session_creation -v
```

---

### 3. `test_websocket_streaming.py`
WebSocket streaming STT test script.

**What it tests:**
- HTTP polling method
- WebSocket streaming method
- Real-time transcription
- Connection handling

**Requirements:**
```bash
pip install aiohttp websockets
```

**Run:**
```bash
python tests/test_websocket_streaming.py
```

---

## Quick Start

### 1. Ensure Services Are Running

```bash
docker compose -f docker-compose-single.yml up -d
docker compose -f docker-compose-single.yml ps
```

### 2. Install Test Dependencies

```bash
pip install pytest pytest-asyncio aiohttp websockets requests
```

### 3. Run All Tests

```bash
# Simple endpoint tests
python tests/test_endpoints_simple.py

# Streaming ASR tests
pytest tests/test_streaming_asr.py -v

# WebSocket tests
python tests/test_websocket_streaming.py
```

---

## Test Coverage

| Component | Test | Status |
|-----------|------|--------|
| API Gateway | `test_endpoints_simple.py` | ✓ |
| Upload/Download | `test_endpoints_simple.py` | ✓ |
| Job Management | `test_endpoints_simple.py` | ✓ |
| Streaming (VAD) | `test_streaming_asr.py` | ✓ |
| Streaming (Buffer) | `test_streaming_asr.py` | ✓ |
| Streaming (Whisper) | `test_streaming_asr.py` | ✓ |
| WebSocket | `test_websocket_streaming.py` | ✓ |
| Metrics | `test_streaming_asr.py` | ✓ |

---

## Troubleshooting

### "Connection refused"

Services not running:
```bash
docker compose -f docker-compose-single.yml up -d
```

### "Module not found"

Install dependencies:
```bash
pip install -r requirements.txt
```

### "Audio file not found"

Ensure file exists:
```bash
ls -la audio/sample_audio.mp3
```

Or use a cloud URL:
```bash
AUDIO_FILE=https://example.com/audio.mp3 python tests/test_endpoints_simple.py
```

### WebSocket connection fails

Check API is running:
```bash
curl http://localhost:8000/health
```

---

## Performance Testing

### Load Testing

```bash
# Multiple concurrent uploads
for i in {1..10}; do
  python tests/test_endpoints_simple.py &
done
wait
```

### Streaming Latency

```bash
pytest tests/test_streaming_asr.py -v -k latency
```

---

## CI/CD Integration

Tests run automatically on:
- Pull requests to `main` or `develop`
- Pushes to `main` branch
- Manual workflow trigger

See [.github/workflows/tests.yml](../.github/workflows/tests.yml)

---

## Writing New Tests

### Example Test

```python
import pytest
import requests

API_BASE = "http://localhost:8000"

@pytest.fixture
def api_health():
    """Test API is healthy"""
    response = requests.get(f"{API_BASE}/health")
    response.raise_for_status()
    return response.json()

def test_api_health(api_health):
    assert api_health['status'] == 'healthy'
```

Run it:
```bash
pytest tests/your_test.py -v
```

---

## Best Practices

1. **Always check services are running first**
   ```bash
   docker compose -f docker-compose-single.yml ps
   ```

2. **Use environment variables for configuration**
   ```bash
   export AUDIO_FILE=path/to/audio.mp3
   python tests/test_endpoints_simple.py
   ```

3. **Clean up test data**
   ```bash
   docker exec stt-redis redis-cli FLUSHALL
   ```

4. **Check logs on failure**
   ```bash
   docker compose -f docker-compose-single.yml logs stt-app
   ```

5. **Run tests in order** (endpoints → streaming → websocket)

---

## Support

- **GitHub Issues**: https://github.com/yuvasisai18/ffmpeg/issues
- **Documentation**: See [../docs/](../docs/) folder
