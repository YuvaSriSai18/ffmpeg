"""Streaming Audio Processor - Main orchestrator for real-time ASR.

Manages complete streaming pipeline:
- Audio chunk ingestion (20-40ms frames)
- VAD for silence filtering
- FFmpeg pass-through processing
- Whisper sliding-window inference
- Partial/final transcript emission
- Redis session persistence
- Backpressure and graceful degradation
"""

import logging
import asyncio
import json
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class StreamingAudioProcessor:
    """
    Main processor for streaming audio transcription.
    
    Flow:
    1. Receive PCM chunk (20-40ms)
    2. Validate format
    3. Run VAD (skip silence)
    4. Buffer audio
    5. Accumulate 2-5 seconds
    6. Run Whisper inference
    7. Emit partial results
    8. On utterance end -> emit final result
    """
    
    def __init__(
        self,
        session_id: str,
        buffer_manager,
        ffmpeg_manager,
        vad_manager,
        whisper_manager,
        metrics_collector,
        redis_client,
    ):
        """
        Initialize processor.
        
        Args:
            session_id: Unique session ID
            buffer_manager: RollingAudioBuffer manager
            ffmpeg_manager: FFmpegManager
            vad_manager: VAD session manager
            whisper_manager: WhisperInferenceManager
            metrics_collector: MetricsCollector
            redis_client: Redis client
        """
        self.session_id = session_id
        self.buffer_manager = buffer_manager
        self.ffmpeg_manager = ffmpeg_manager
        self.vad_manager = vad_manager
        self.whisper_manager = whisper_manager
        self.metrics_collector = metrics_collector
        self.redis_client = redis_client
        
        # Session state
        self.is_active = False
        self.total_chunks_received = 0
        self.total_voiced_chunks = 0
        self.utterance_in_progress = False
        
        logger.info(f"[{session_id}] StreamingAudioProcessor initialized")
    
    async def start_session(self) -> bool:
        """
        Start streaming session.
        
        Initializes all components for this session.
        """
        try:
            logger.info(f"[{self.session_id}] Starting session")
            
            # Initialize buffer
            self.buffer = self.buffer_manager.get_or_create_buffer(
                self.session_id
            )
            
            # Initialize FFmpeg pipeline
            success = await self.ffmpeg_manager.start_pipeline(self.session_id)
            if not success:
                logger.error(f"[{self.session_id}] Failed to start FFmpeg")
                return False
            
            # Initialize VAD
            self.vad_session = self.vad_manager.get_or_create_session(
                self.session_id
            )
            
            # Initialize Whisper inference
            self.inference_session = self.whisper_manager.get_or_create_session(
                self.session_id
            )
            
            # Store session in Redis
            await self.redis_client.set_session_state(
                self.session_id,
                {
                    "status": "active",
                    "start_time": datetime.now().isoformat(),
                    "total_chunks": 0,
                    "voiced_chunks": 0,
                }
            )
            
            self.is_active = True
            self.metrics_collector.record_stage(self.session_id, "session_start")
            
            logger.info(f"[{self.session_id}] Session started successfully")
            return True
        
        except Exception as e:
            logger.error(
                f"[{self.session_id}] Failed to start session: {e}",
                exc_info=True
            )
            return False
    
    async def process_audio_chunk(
        self,
        chunk_bytes: bytes,
    ) -> Dict[str, Any]:
        """
        Process incoming audio chunk.
        
        Main processing pipeline for each frame.
        
        Args:
            chunk_bytes: Raw PCM audio chunk
            
        Returns:
            Dict with processing result
        """
        if not self.is_active:
            return {"success": False, "error": "Session not active"}
        
        try:
            # Stage 1: Track metrics
            self.metrics_collector.record_stage(self.session_id, "chunk_received")
            
            # Stage 2: Validate chunk
            success, msg = self.buffer.push_chunk(chunk_bytes)
            if not success:
                logger.warning(f"[{self.session_id}] Chunk validation failed: {msg}")
                return {"success": False, "error": msg}
            
            self.total_chunks_received += 1
            
            # Stage 3: Run VAD
            self.metrics_collector.record_stage(self.session_id, "vad_start")
            
            # Convert bytes to numpy array for VAD
            import numpy as np
            chunk_samples = np.frombuffer(chunk_bytes, dtype=np.int16)
            
            vad_result = self.vad_session.process_frame(chunk_samples)
            is_speech = vad_result["is_speech"]
            utterance_end = vad_result["utterance_end"]
            
            self.metrics_collector.record_stage(self.session_id, "vad_end")
            
            # Track speech
            if is_speech:
                self.total_voiced_chunks += 1
                self.utterance_in_progress = True
            
            # Stage 4: Get current buffer
            self.metrics_collector.record_stage(self.session_id, "buffer_read")
            current_buffer = self.buffer.get_buffer()
            buffer_duration_ms = self.buffer.get_buffer_duration_ms()
            
            # Stage 5: Check if ready for inference (2+ seconds of audio)
            result = {
                "session_id": self.session_id,
                "success": True,
                "chunk_index": self.total_chunks_received,
                "is_speech": is_speech,
                "utterance_end": utterance_end,
                "buffer_duration_ms": buffer_duration_ms,
                "inference_triggered": False,
                "events": [],
            }
            
            # Only infer on speech, not silence
            if is_speech and buffer_duration_ms >= 2000:
                self.metrics_collector.record_stage(self.session_id, "inference_start")
                
                # Run Whisper
                inference_result = await self.inference_session.infer_chunk(
                    current_buffer
                )
                
                self.metrics_collector.record_stage(self.session_id, "inference_end")
                
                if inference_result:
                    result["inference_triggered"] = True
                    
                    # Get partial result
                    partial = self.inference_session.get_partial_result()
                    
                    # Emit partial result
                    await self.redis_client.publish_transcript_chunk(
                        self.session_id,
                        partial["text"],
                        0.0,
                        0.0,
                        0.95,
                    )
                    
                    result["events"].append({
                        "type": "partial_result",
                        "text": partial["text"],
                        "new_text": partial.get("new_text", ""),
                    })
                    
                    logger.info(
                        f"[{self.session_id}] Partial: '{partial['new_text']}'"
                    )
            
            # Stage 6: Handle utterance end
            if utterance_end and self.utterance_in_progress:
                logger.info(f"[{self.session_id}] Utterance end detected")
                
                # Force final inference
                if len(current_buffer) > 0:
                    inference_result = await self.inference_session.infer_chunk(
                        current_buffer
                    )
                
                # Get final result
                final = self.inference_session.get_final_result()
                
                # Emit final result
                await self.redis_client.publish_transcript_chunk(
                    self.session_id,
                    final["text"],
                    0.0,
                    0.0,
                    1.0,  # Confidence 1.0 for final
                )
                
                result["events"].append({
                    "type": "final_result",
                    "text": final["text"],
                })
                
                # Reset for next utterance
                self.buffer.clear_buffer()
                self.inference_session.reset()
                self.vad_session.reset()
                self.utterance_in_progress = False
                
                logger.info(f"[{self.session_id}] Final: '{final['text']}'")
            
            # Stage 7: Update Redis session
            await self.redis_client.set_session_state(
                self.session_id,
                {
                    "status": "processing",
                    "total_chunks": self.total_chunks_received,
                    "voiced_chunks": self.total_voiced_chunks,
                    "buffer_duration_ms": buffer_duration_ms,
                    "last_update": datetime.now().isoformat(),
                }
            )
            
            self.metrics_collector.record_stage(self.session_id, "chunk_processed")
            
            return result
        
        except Exception as e:
            logger.error(
                f"[{self.session_id}] Error processing chunk: {e}",
                exc_info=True
            )
            return {"success": False, "error": str(e)}
    
    async def handle_control_event(self, event_type: str) -> bool:
        """
        Handle control events from upstream.
        
        Args:
            event_type: Control event type (start_session, stop_session, flush)
            
        Returns:
            Success status
        """
        logger.info(f"[{self.session_id}] Control event: {event_type}")
        
        if event_type == "flush":
            # Force final inference
            current_buffer = self.buffer.get_buffer()
            if len(current_buffer) > 0:
                inference_result = await self.inference_session.infer_chunk(
                    current_buffer
                )
                final = self.inference_session.get_final_result()
                await self.redis_client.publish_transcript_chunk(
                    self.session_id,
                    final["text"],
                    0.0,
                    0.0,
                    1.0,
                )
            self.buffer.clear_buffer()
            self.inference_session.reset()
            return True
        
        elif event_type == "stop_session":
            return await self.stop_session()
        
        return False
    
    async def stop_session(self) -> bool:
        """
        Stop streaming session and cleanup.
        
        Returns:
            Success status
        """
        try:
            logger.info(f"[{self.session_id}] Stopping session")
            
            if not self.is_active:
                return True
            
            # Get final metrics
            metrics = self.metrics_collector.trackers.get(self.session_id)
            if metrics:
                stats = metrics.get_all_stats()
                logger.info(f"[{self.session_id}] Final metrics: {stats}")
            
            # Cleanup resources
            self.ffmpeg_manager.pipelines.pop(self.session_id, None)
            self.buffer_manager.release_buffer(self.session_id)
            self.whisper_manager.release_session(self.session_id)
            self.metrics_collector.release_session(self.session_id)
            
            # Update Redis
            await self.redis_client.set_session_state(
                self.session_id,
                {
                    "status": "completed",
                    "end_time": datetime.now().isoformat(),
                    "total_chunks": self.total_chunks_received,
                    "voiced_chunks": self.total_voiced_chunks,
                }
            )
            
            # Set TTL on session key
            await self.redis_client.set_session_ttl(self.session_id, 3600)
            
            self.is_active = False
            
            logger.info(f"[{self.session_id}] Session stopped")
            return True
        
        except Exception as e:
            logger.error(
                f"[{self.session_id}] Error stopping session: {e}",
                exc_info=True
            )
            return False
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        return {
            "session_id": self.session_id,
            "is_active": self.is_active,
            "total_chunks_received": self.total_chunks_received,
            "total_voiced_chunks": self.total_voiced_chunks,
            "buffer": self.buffer.get_stats() if hasattr(self, 'buffer') else None,
            "vad": self.vad_session.get_stats() if hasattr(self, 'vad_session') else None,
            "inference": self.inference_session.get_stats() if hasattr(self, 'inference_session') else None,
        }
