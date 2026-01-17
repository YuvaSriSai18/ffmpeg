"""FFmpeg streaming pipeline for real-time audio processing.

Manages FFmpeg process for:
- Streaming PCM input via stdin
- Streaming processed audio via stdout
- Per-session process management
- Graceful cleanup on disconnect
"""

import asyncio
import logging
import numpy as np
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class FFmpegStreamingPipeline:
    """
    Manages FFmpeg subprocess for streaming audio processing.
    
    One process per session - audio flows:
    stdin (PCM 16kHz mono) -> FFmpeg -> stdout (PCM 16kHz mono)
    """
    
    def __init__(self, session_id: str):
        """
        Initialize FFmpeg pipeline.
        
        Args:
            session_id: Unique session identifier
        """
        self.session_id = session_id
        self.process: Optional[asyncio.subprocess.Process] = None
        self.is_running = False
        self.stats = {
            "bytes_input": 0,
            "bytes_output": 0,
            "chunks_received": 0,
            "chunks_sent": 0,
            "start_time": datetime.now(),
        }
    
    async def start(self) -> bool:
        """
        Start FFmpeg process.
        
        FFmpeg command:
        - Input: raw PCM 16kHz mono 16-bit from stdin
        - Output: same format to stdout (no transcoding)
        - Real-time mode (no buffering, no seeking)
        
        Returns:
            True if started successfully
        """
        try:
            if self.is_running:
                logger.warning(f"[{self.session_id}] FFmpeg already running")
                return False
            
            # FFmpeg command for pass-through audio (no transcoding)
            # Use pipe:0 for stdin and pipe:1 for stdout
            cmd = [
                "ffmpeg",
                # Input from stdin
                "-i", "pipe:0",
                # Input format: raw PCM, 16kHz, mono, 16-bit
                "-f", "s16le",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                # Output to stdout
                "-f", "s16le",
                "pipe:1",
            ]
            
            # Start FFmpeg process
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            self.is_running = True
            logger.info(
                f"[{self.session_id}] FFmpeg process started (PID: {self.process.pid})"
            )
            
            return True
        
        except FileNotFoundError:
            logger.error(
                f"[{self.session_id}] FFmpeg not found in PATH. "
                "Please install ffmpeg."
            )
            self.is_running = False
            return False
        
        except Exception as e:
            logger.error(
                f"[{self.session_id}] Failed to start FFmpeg: {e}",
                exc_info=True
            )
            self.is_running = False
            return False
    
    async def write_audio_chunk(self, chunk_bytes: bytes) -> bool:
        """
        Write audio chunk to FFmpeg stdin.
        
        This is NON-BLOCKING - data is queued for FFmpeg.
        FFmpeg processes continuously without waiting for EOF.
        
        Args:
            chunk_bytes: Raw PCM audio chunk
            
        Returns:
            True if written successfully
        """
        if not self.is_running or self.process is None:
            logger.error(
                f"[{self.session_id}] FFmpeg process not running"
            )
            return False
        
        try:
            # Write to stdin
            self.process.stdin.write(chunk_bytes)
            await self.process.stdin.drain()
            
            self.stats["bytes_input"] += len(chunk_bytes)
            self.stats["chunks_received"] += 1
            
            return True
        
        except BrokenPipeError:
            logger.error(f"[{self.session_id}] FFmpeg stdin pipe broken")
            self.is_running = False
            return False
        
        except Exception as e:
            logger.error(
                f"[{self.session_id}] Error writing to FFmpeg: {e}",
                exc_info=True
            )
            self.is_running = False
            return False
    
    async def read_audio_chunk(self, chunk_size: int = 1024) -> Optional[bytes]:
        """
        Read processed audio from FFmpeg stdout (non-blocking).
        
        FFmpeg outputs audio incrementally as it's processed.
        Read whatever is available without waiting for full chunk.
        
        Args:
            chunk_size: Max bytes to read
            
        Returns:
            Audio chunk bytes, or None if error
        """
        if not self.is_running or self.process is None:
            return None
        
        try:
            # Non-blocking read attempt
            chunk = await asyncio.wait_for(
                self.process.stdout.readexactly(chunk_size),
                timeout=0.1
            )
            
            self.stats["bytes_output"] += len(chunk)
            self.stats["chunks_sent"] += 1
            
            return chunk
        
        except asyncio.TimeoutError:
            # No data available (normal in streaming)
            return None
        
        except asyncio.IncompleteReadError as e:
            # Partial read (EOF or error)
            if e.partial:
                self.stats["bytes_output"] += len(e.partial)
                self.stats["chunks_sent"] += 1
                return e.partial
            return None
        
        except Exception as e:
            logger.error(
                f"[{self.session_id}] Error reading from FFmpeg: {e}",
                exc_info=True
            )
            return None
    
    async def stop(self, timeout_seconds: float = 5.0) -> bool:
        """
        Stop FFmpeg process gracefully.
        
        Args:
            timeout_seconds: Timeout for graceful shutdown
            
        Returns:
            True if stopped cleanly
        """
        if not self.is_running or self.process is None:
            logger.debug(f"[{self.session_id}] FFmpeg already stopped")
            return True
        
        try:
            logger.info(f"[{self.session_id}] Stopping FFmpeg process")
            
            # Close stdin to signal EOF to FFmpeg
            self.process.stdin.close()
            await self.process.stdin.wait_closed()
            
            # Wait for process to terminate
            try:
                await asyncio.wait_for(
                    self.process.wait(),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"[{self.session_id}] FFmpeg didn't terminate gracefully, "
                    "killing..."
                )
                self.process.kill()
                await self.process.wait()
            
            self.is_running = False
            logger.info(
                f"[{self.session_id}] FFmpeg process stopped cleanly"
            )
            
            return True
        
        except Exception as e:
            logger.error(
                f"[{self.session_id}] Error stopping FFmpeg: {e}",
                exc_info=True
            )
            if self.process:
                try:
                    self.process.kill()
                except:
                    pass
            self.is_running = False
            return False
    
    async def close(self):
        """Cleanup and close all resources."""
        await self.stop()
    
    def get_stats(self) -> dict:
        """Get pipeline statistics."""
        duration = (
            datetime.now() - self.stats["start_time"]
        ).total_seconds()
        
        return {
            "session_id": self.session_id,
            "is_running": self.is_running,
            "duration_seconds": duration,
            "bytes_input": self.stats["bytes_input"],
            "bytes_output": self.stats["bytes_output"],
            "chunks_received": self.stats["chunks_received"],
            "chunks_sent": self.stats["chunks_sent"],
        }
    
    async def __aenter__(self):
        """Context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()


class FFmpegManager:
    """Manages FFmpeg pipelines for multiple concurrent sessions."""
    
    def __init__(self):
        """Initialize manager."""
        self.pipelines: dict = {}
    
    def get_or_create_pipeline(self, session_id: str) -> FFmpegStreamingPipeline:
        """Get existing or create new pipeline for session."""
        if session_id not in self.pipelines:
            self.pipelines[session_id] = FFmpegStreamingPipeline(session_id)
            logger.debug(f"Created FFmpeg pipeline for session {session_id}")
        
        return self.pipelines[session_id]
    
    async def start_pipeline(self, session_id: str) -> bool:
        """Start FFmpeg pipeline for session."""
        pipeline = self.get_or_create_pipeline(session_id)
        return await pipeline.start()
    
    async def stop_pipeline(self, session_id: str) -> bool:
        """Stop and remove FFmpeg pipeline for session."""
        if session_id in self.pipelines:
            pipeline = self.pipelines[session_id]
            success = await pipeline.stop()
            del self.pipelines[session_id]
            logger.info(f"Stopped and removed pipeline for {session_id}")
            return success
        return True
    
    def get_all_stats(self) -> dict:
        """Get stats for all active pipelines."""
        return {
            session_id: pipeline.get_stats()
            for session_id, pipeline in self.pipelines.items()
        }
    
    async def cleanup_all(self):
        """Stop all pipelines."""
        session_ids = list(self.pipelines.keys())
        for session_id in session_ids:
            await self.stop_pipeline(session_id)
        logger.info(f"Cleaned up {len(session_ids)} FFmpeg pipelines")
