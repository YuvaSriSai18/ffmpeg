# conftest.py - Pytest Configuration

import pytest
import os
import subprocess
import time

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
SERVICES_TIMEOUT = 30  # seconds


@pytest.fixture(scope="session", autouse=True)
def check_services_running():
    """Ensure Docker services are running before running tests."""
    import requests
    
    print("\nChecking if services are running...")
    
    start_time = time.time()
    while time.time() - start_time < SERVICES_TIMEOUT:
        try:
            response = requests.get(f"{API_BASE_URL}/health", timeout=2)
            if response.status_code == 200:
                print("✓ Services are running")
                return True
        except Exception:
            pass
        
        print(".", end="", flush=True)
        time.sleep(1)
    
    print("\n✗ Services not responding. Start them with:")
    print("  docker compose -f docker-compose-single.yml up -d")
    raise Exception("Services not running")


@pytest.fixture
def api_client():
    """Provide an API client for tests."""
    import requests
    class APIClient:
        def __init__(self, base_url):
            self.base_url = base_url
            self.session = requests.Session()
        
        def get(self, endpoint):
            return self.session.get(f"{self.base_url}{endpoint}")
        
        def post(self, endpoint, **kwargs):
            return self.session.post(f"{self.base_url}{endpoint}", **kwargs)
        
        def close(self):
            self.session.close()
    
    client = APIClient(API_BASE_URL)
    yield client
    client.close()


@pytest.fixture
def redis_client():
    """Provide a Redis client for tests."""
    try:
        import redis
        return redis.Redis(host='localhost', port=6379, decode_responses=True)
    except Exception:
        pytest.skip("Redis not available")
