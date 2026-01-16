"""Redis client utilities for async operations."""
import redis.asyncio as redis
from typing import Optional, Any, Dict
import json
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client wrapper."""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        """Connect to Redis."""
        try:
            self.client = await redis.from_url(self.redis_url, decode_responses=True)
            await self.client.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            logger.info("Disconnected from Redis")

    async def set_job_status(
        self,
        job_id: str,
        status: str,
        ttl_hours: int = 24,
    ):
        """Set job status with TTL."""
        key = f"stt:jobs:{job_id}:status"
        await self.client.setex(
            key,
            timedelta(hours=ttl_hours),
            status,
        )
        logger.debug(f"Set job {job_id} status to {status}")

    async def get_job_status(self, job_id: str) -> Optional[str]:
        """Get current job status."""
        key = f"stt:jobs:{job_id}:status"
        status = await self.client.get(key)
        return status

    async def set_job_metadata(
        self,
        job_id: str,
        metadata: Dict[str, Any],
        ttl_hours: int = 24,
    ):
        """Set job metadata as JSON."""
        key = f"stt:jobs:{job_id}:meta"
        await self.client.setex(
            key,
            timedelta(hours=ttl_hours),
            json.dumps(metadata),
        )
        logger.debug(f"Set metadata for job {job_id}")

    async def get_job_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job metadata."""
        key = f"stt:jobs:{job_id}:meta"
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None

    async def set_job_result(
        self,
        job_id: str,
        result: Dict[str, Any],
        ttl_hours: int = 24,
    ):
        """Set job transcription result as JSON."""
        key = f"stt:jobs:{job_id}:result"
        await self.client.setex(
            key,
            timedelta(hours=ttl_hours),
            json.dumps(result),
        )
        logger.debug(f"Set result for job {job_id}")

    async def get_job_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job transcription result."""
        key = f"stt:jobs:{job_id}:result"
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None

    async def publish(self, channel: str, message: str):
        """Publish message to channel."""
        await self.client.publish(channel, message)
        logger.debug(f"Published to {channel}: {message[:100]}...")

    async def subscribe(self, channel: str):
        """Subscribe to channel and return pubsub object."""
        pubsub = self.client.pubsub()
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed to channel: {channel}")
        return pubsub

    async def push_job(self, queue_name: str, message: str):
        """Push a job message onto a queue."""
        await self.client.rpush(queue_name, message)
        logger.debug(f"Pushed job to {queue_name}")

    async def pop_job(self, queue_name: str, timeout: int = 1) -> Optional[str]:
        """
        Pop a job from queue with blocking timeout (in seconds).
        Returns None if timeout occurs.
        """
        result = await self.client.blpop(queue_name, timeout)
        if result:
            # blpop returns tuple (queue_name, value)
            return result[1]
        return None

    async def delete_key(self, key: str):
        """Delete a key from Redis."""
        await self.client.delete(key)
        logger.debug(f"Deleted key: {key}")

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        result = await self.client.exists(key)
        return result == 1
