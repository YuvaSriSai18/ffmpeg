"""Audio Rolling Buffer with streaming validation and backpressure.

Maintains bounded in-memory buffer for streaming audio with:
- Chunk size validation (20-40ms @ 16kHz)
- Bounded memory (prevents unbounded growth)
- Graceful frame dropping under backpressure
- Per-session state tracking
"""

import logging
from typing import Optional, Tuple
from collections import deque
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


class AudioChunkValidator:
    """Validates incoming audio chunks meet streaming requirements."""
    
    # Audio constraints
    SAMPLE_RATE = 16000  # Hz
    CHANNELS = 1
    SAMPLE_WIDTH = 2  # bytes (16-bit)
    
    # Acceptable frame duration: 20-40ms
    MIN_FRAME_MS = 20
    MAX_FRAME_MS = 40
    
    def __init__(self):
        """Initialize validator."""
        # Frame sizes in bytes
        self.min_frame_samples = (
            self.SAMPLE_RATE * self.MIN_FRAME_MS // 1000
        )
        self.max_frame_samples = (
            self.SAMPLE_RATE * self.MAX_FRAME_MS // 1000
        )
        self.min_frame_bytes = self.min_frame_samples * self.SAMPLE_WIDTH
        self.max_frame_bytes = self.max_frame_samples * self.SAMPLE_WIDTH
    
    def validate(self, chunk_bytes: bytes) -> Tuple[bool, str]:
        """
        Validate incoming audio chunk.
        
        Args:
            chunk_bytes: Raw audio chunk
            
        Returns:
            Tuple of (is_valid, message)
        """
        chunk_size = len(chunk_bytes)
        
        # Check size bounds
        if chunk_size < self.min_frame_bytes:
            return False, (
                f"Chunk too small: {chunk_size} bytes "
                f"(min {self.min_frame_bytes})"
            )
        
        if chunk_size > self.max_frame_bytes:
            return False, (
                f"Chunk too large: {chunk_size} bytes "
                f"(max {self.max_frame_bytes})"
            )
        
        # Check alignment (must be multiple of sample width)
        if chunk_size % self.SAMPLE_WIDTH != 0:
            return False, (
                f"Chunk size not aligned: {chunk_size} bytes "
                f"(must be multiple of {self.SAMPLE_WIDTH})"
            )
        
        return True, "Valid"


class RollingAudioBuffer:
    """
    Bounded rolling buffer for streaming audio.
    
    Features:
    - Stores up to 5 seconds of audio
    - Rejects frames gracefully if buffer full
    - Tracks buffer fill rate (backpressure)
    - Per-session state
    """
    
    def __init__(
        self,
        session_id: str,
        sample_rate: int = 16000,
        max_duration_seconds: float = 5.0,
    ):
        """
        Initialize rolling buffer.
        
        Args:
            session_id: Unique session identifier
            sample_rate: Audio sample rate (Hz)
            max_duration_seconds: Maximum buffer duration in seconds
        """
        self.session_id = session_id
        self.sample_rate = sample_rate
        self.max_duration_seconds = max_duration_seconds
        
        # Calculate max samples
        self.max_samples = int(sample_rate * max_duration_seconds)
        
        # Ring buffer (deque is efficient for FIFO)
        self.buffer: deque = deque(maxlen=self.max_samples)
        
        # Tracking
        self.total_samples_received = 0
        self.frames_dropped = 0
        self.peak_fill_ratio = 0.0
        self.validator = AudioChunkValidator()
    
    def push_chunk(self, chunk_bytes: bytes) -> Tuple[bool, str]:
        """
        Push audio chunk to buffer.
        
        Args:
            chunk_bytes: Raw PCM audio chunk
            
        Returns:
            Tuple of (success, message)
        """
        # Validate chunk
        is_valid, msg = self.validator.validate(chunk_bytes)
        if not is_valid:
            logger.warning(f"[{self.session_id}] Chunk validation failed: {msg}")
            self.frames_dropped += 1
            return False, msg
        
        # Convert bytes to samples
        chunk_samples = np.frombuffer(chunk_bytes, dtype=np.int16)
        
        # Check buffer fill before adding
        current_fill = len(self.buffer)
        fill_ratio = current_fill / self.max_samples if self.max_samples > 0 else 0
        
        # Update peak
        self.peak_fill_ratio = max(self.peak_fill_ratio, fill_ratio)
        
        # Backpressure: if buffer is 90%+ full, drop frames
        if fill_ratio > 0.9:
            logger.warning(
                f"[{self.session_id}] Buffer backpressure: {fill_ratio:.1%} full, "
                f"dropping frame"
            )
            self.frames_dropped += 1
            return False, "Buffer backpressure: dropping frame"
        
        # Add samples to buffer
        self.buffer.extend(chunk_samples)
        self.total_samples_received += len(chunk_samples)
        
        return True, (
            f"Pushed {len(chunk_samples)} samples "
            f"(buffer {fill_ratio:.1%} full)"
        )
    
    def get_buffer(self) -> np.ndarray:
        """
        Get current buffer content as numpy array.
        
        Returns:
            NumPy array of samples currently in buffer
        """
        if len(self.buffer) == 0:
            return np.array([], dtype=np.int16)
        return np.array(list(self.buffer), dtype=np.int16)
    
    def get_buffer_duration_ms(self) -> float:
        """Get current buffer duration in milliseconds."""
        if self.sample_rate == 0:
            return 0.0
        return (len(self.buffer) / self.sample_rate) * 1000
    
    def clear_buffer(self):
        """Clear buffer (call after processing utterance)."""
        old_size = len(self.buffer)
        self.buffer.clear()
        logger.debug(
            f"[{self.session_id}] Buffer cleared ({old_size} samples)"
        )
    
    def get_stats(self) -> dict:
        """Get buffer statistics."""
        buffer_duration_s = len(self.buffer) / self.sample_rate
        
        return {
            "session_id": self.session_id,
            "current_samples": len(self.buffer),
            "max_samples": self.max_samples,
            "current_duration_ms": self.get_buffer_duration_ms(),
            "max_duration_seconds": self.max_duration_seconds,
            "fill_ratio": len(self.buffer) / self.max_samples if self.max_samples > 0 else 0,
            "peak_fill_ratio": self.peak_fill_ratio,
            "total_samples_received": self.total_samples_received,
            "frames_dropped": self.frames_dropped,
        }


class BufferManager:
    """Manages rolling buffers for multiple concurrent sessions."""
    
    def __init__(self, default_max_duration: float = 5.0):
        """Initialize buffer manager."""
        self.buffers: dict = {}
        self.default_max_duration = default_max_duration
    
    def get_or_create_buffer(
        self,
        session_id: str,
        sample_rate: int = 16000,
    ) -> RollingAudioBuffer:
        """Get existing or create new buffer for session."""
        if session_id not in self.buffers:
            self.buffers[session_id] = RollingAudioBuffer(
                session_id=session_id,
                sample_rate=sample_rate,
                max_duration_seconds=self.default_max_duration,
            )
            logger.debug(f"Created buffer for session {session_id}")
        
        return self.buffers[session_id]
    
    def release_buffer(self, session_id: str):
        """Release buffer for session (cleanup)."""
        if session_id in self.buffers:
            stats = self.buffers[session_id].get_stats()
            logger.info(f"Releasing buffer for {session_id}: {stats}")
            del self.buffers[session_id]
    
    def get_all_stats(self) -> dict:
        """Get stats for all active buffers."""
        return {
            session_id: buf.get_stats()
            for session_id, buf in self.buffers.items()
        }
    
    def cleanup_all(self):
        """Clear all buffers."""
        session_ids = list(self.buffers.keys())
        for session_id in session_ids:
            self.release_buffer(session_id)
        logger.info(f"Cleaned up {len(session_ids)} buffers")
