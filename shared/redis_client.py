"""Redis client utilities for async operations."""
import redis.asyncio as redis
from typing import Optional, Any, Dict
import json
import logging
from datetime import timedelta, datetime

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
    # ==================== WebSocket Pub/Sub Methods ====================

    async def publish_audio_chunk(
        self,
        job_id: str,
        chunk_data: str,
        chunk_index: int
    ) -> int:
        """
        Publish audio chunk for streaming processing.
        
        WHY: Stream audio chunks in real-time to processors
        Instead of waiting for entire file upload.
        
        Args:
            job_id: Unique job identifier
            chunk_data: Base64 encoded audio chunk
            chunk_index: Sequence number for ordering
            
        Returns:
            Number of subscribers that received message
        """
        message = json.dumps({
            "chunk_index": chunk_index,
            "data": chunk_data,
            "timestamp": datetime.utcnow().isoformat()
        })
        return await self.client.publish(
            f"stt:audio:{job_id}",
            message
        )

    async def publish_transcript_chunk(
        self,
        job_id: str,
        text: str,
        start_time: float,
        end_time: float,
        confidence: float = 0.95
    ) -> int:
        """
        Publish transcription result chunk in real-time.
        
        WHY: Stream transcript results as Whisper processes
        User sees transcription appearing word-by-word.
        
        Args:
            job_id: Unique job identifier
            text: Transcribed text segment
            start_time: Audio start timestamp (seconds)
            end_time: Audio end timestamp (seconds)
            confidence: Confidence score (0.0-1.0)
        """
        message = json.dumps({
            "text": text,
            "start": start_time,
            "end": end_time,
            "confidence": confidence,
            "timestamp": datetime.utcnow().isoformat()
        })
        return await self.client.publish(
            f"stt:results:{job_id}",
            message
        )

    async def publish_stream_status(
        self,
        job_id: str,
        status: str,
        details: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Publish job status update for streaming connection.
        
        WHY: Notify WebSocket client of job state changes
        Client updates UI instantly without polling.
        
        Args:
            job_id: Unique job identifier
            status: Current job status (e.g., 'receiving', 'processing')
            details: Additional status details
        """
        message = json.dumps({
            "status": status,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat()
        })
        return await self.client.publish(
            f"stt:status:{job_id}",
            message
        )

    async def subscribe_audio_chunks(self, job_id: str):
        """
        Subscribe to audio chunks for streaming processing.
        
        WHY: Audio Processor listens for incoming audio chunks
        Processes them as they arrive (streaming mode).
        """
        pubsub = self.client.pubsub()
        await pubsub.subscribe(f"stt:audio:{job_id}")
        logger.info(f"Subscribed to audio chunks for {job_id}")
        return pubsub

    async def subscribe_transcript_results(self, job_id: str):
        """
        Subscribe to transcript results.
        
        WHY: API Gateway listens to transcriber results
        Forwards them to WebSocket client in real-time.
        """
        pubsub = self.client.pubsub()
        await pubsub.subscribe(f"stt:results:{job_id}")
        logger.info(f"Subscribed to transcript results for {job_id}")
        return pubsub

    async def subscribe_stream_status(self, job_id: str):
        """
        Subscribe to stream status updates.
        
        WHY: WebSocket client listens to job status
        Updates progress bar or status display.
        """
        pubsub = self.client.pubsub()
        await pubsub.subscribe(f"stt:status:{job_id}")
        logger.info(f"Subscribed to status updates for {job_id}")
        return pubsub

    async def unsubscribe_all(self, pubsub):
        """Clean up subscription."""
        await pubsub.unsubscribe()
        await pubsub.close()
        logger.debug("Unsubscribed from all channels")
    
    # ==================== Streaming Session State Methods ====================
    
    async def set_session_state(
        self,
        session_id: str,
        state: Dict[str, Any],
        ttl_seconds: int = 3600,
    ):
        """
        Set streaming session state (worker-safe).
        
        Args:
            session_id: Unique session ID
            state: Session state dictionary
            ttl_seconds: Time to live in seconds
        """
        key = f"stt:stream:session:{session_id}"
        await self.client.setex(
            key,
            ttl_seconds,
            json.dumps(state),
        )
        logger.debug(f"Set session state for {session_id}")
    
    async def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get streaming session state."""
        key = f"stt:stream:session:{session_id}"
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None
    
    async def set_session_ttl(self, session_id: str, ttl_seconds: int):
        """Set TTL on session key for automatic cleanup."""
        key = f"stt:stream:session:{session_id}"
        await self.client.expire(key, ttl_seconds)
        logger.debug(f"Set TTL {ttl_seconds}s for session {session_id}")
    
    async def store_last_audio_timestamp(
        self,
        session_id: str,
        timestamp_ms: float,
    ):
        """Store last audio timestamp for session resume."""
        key = f"stt:stream:session:{session_id}:last_audio_ts"
        await self.client.set(key, str(timestamp_ms))
    
    async def get_last_audio_timestamp(self, session_id: str) -> Optional[float]:
        """Get last audio timestamp."""
        key = f"stt:stream:session:{session_id}:last_audio_ts"
        value = await self.client.get(key)
        return float(value) if value else None
    
    async def store_transcript_offset(
        self,
        session_id: str,
        offset_seconds: float,
    ):
        """Store transcript processing offset."""
        key = f"stt:stream:session:{session_id}:transcript_offset"
        await self.client.set(key, str(offset_seconds))
    
    async def get_transcript_offset(self, session_id: str) -> Optional[float]:
        """Get transcript offset."""
        key = f"stt:stream:session:{session_id}:transcript_offset"
        value = await self.client.get(key)
        return float(value) if value else None
    
    async def store_partial_text(
        self,
        session_id: str,
        text: str,
    ):
        """Store last partial transcription."""
        key = f"stt:stream:session:{session_id}:partial_text"
        await self.client.set(key, text)
    
    async def get_partial_text(self, session_id: str) -> Optional[str]:
        """Get last partial text."""
        key = f"stt:stream:session:{session_id}:partial_text"
        return await self.client.get(key)