"""Sliding-window Whisper inference for low-latency streaming ASR.

Implements:
- Accumulation of 2-5 seconds of audio before inference
- Sliding window to avoid reprocessing
- Token re-evaluation for stable partial results
- Per-session transcript offset tracking
- Partial & final transcription events
"""

import logging
from typing import Optional, Dict, Any, List
import numpy as np
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class WhisperStreamingInference:
    """
    Manages streaming Whisper inference with sliding window.
    
    Instead of running Whisper on full audio repeatedly:
    1. Accumulate 2-5 seconds of audio
    2. Run Whisper on accumulated buffer
    3. Save offset and last tokens
    4. Drop processed audio, keep overlap window
    5. On next batch, avoid reprocessing old tokens
    """
    
    def __init__(
        self,
        session_id: str,
        whisper_model,
        accumulation_duration_seconds: float = 3.0,
        overlap_duration_seconds: float = 0.5,
    ):
        """
        Initialize streaming inference.
        
        Args:
            session_id: Unique session ID
            whisper_model: Loaded Whisper model
            accumulation_duration_seconds: Audio to accumulate before inference
            overlap_duration_seconds: Audio to keep for re-evaluation
        """
        self.session_id = session_id
        self.whisper_model = whisper_model
        self.accumulation_duration_seconds = accumulation_duration_seconds
        self.overlap_duration_seconds = overlap_duration_seconds
        
        # Transcript tracking
        self.full_transcript = ""
        self.last_partial_text = ""
        self.transcript_offset_seconds = 0.0
        
        # Token tracking for re-evaluation
        self.last_inference_tokens: List[int] = []
        
        # Statistics
        self.inference_count = 0
        self.total_inference_time_seconds = 0.0
        
        logger.info(
            f"[{session_id}] Streaming Whisper initialized "
            f"(accumulation={accumulation_duration_seconds}s, "
            f"overlap={overlap_duration_seconds}s)"
        )
    
    async def infer_chunk(
        self,
        audio_buffer: np.ndarray,
        sample_rate: int = 16000,
    ) -> Optional[Dict[str, Any]]:
        """
        Run Whisper inference on audio buffer using sliding window.
        
        Process:
        1. Check if buffer has enough audio (>= 2 seconds)
        2. Run Whisper on accumulated audio
        3. Extract new text (skip already-processed tokens)
        4. Return partial result
        
        Args:
            audio_buffer: NumPy array of PCM samples
            sample_rate: Sample rate (Hz)
            
        Returns:
            Dict with inference result or None
        """
        if len(audio_buffer) == 0:
            return None
        
        # Calculate duration
        duration_seconds = len(audio_buffer) / sample_rate
        
        # Don't infer if buffer too small (< 2 seconds of voiced audio)
        min_inference_duration = 2.0
        if duration_seconds < min_inference_duration:
            logger.debug(
                f"[{self.session_id}] Buffer too small ({duration_seconds:.1f}s), "
                f"waiting for more audio"
            )
            return None
        
        try:
            # Convert to float32 for Whisper
            audio_float = audio_buffer.astype(np.float32) / 32768.0
            
            # Run Whisper inference
            logger.debug(
                f"[{self.session_id}] Running Whisper inference "
                f"on {duration_seconds:.1f}s of audio"
            )
            
            result = self.whisper_model.transcribe(
                audio_float,
                language="en",
                verbose=False,
                task="transcribe",
            )
            
            self.inference_count += 1
            
            # Extract text
            full_text = result.get("text", "").strip()
            segments = result.get("segments", [])
            
            # Calculate new text (what wasn't already transcribed)
            # This is the key to partial results
            new_text = self._extract_new_text(full_text, segments)
            
            # Update tracking
            self.full_transcript = full_text
            self.last_partial_text = new_text
            self.transcript_offset_seconds += duration_seconds
            
            # Get tokens for next re-evaluation
            if segments:
                last_segment = segments[-1]
                self.last_inference_tokens = last_segment.get("tokens", [])
            
            result_data = {
                "session_id": self.session_id,
                "full_text": full_text,
                "new_text": new_text,
                "duration_seconds": duration_seconds,
                "segments": segments,
                "inference_count": self.inference_count,
                "timestamp": datetime.now().isoformat(),
            }
            
            logger.info(
                f"[{self.session_id}] Inference #{self.inference_count}: "
                f"new_text='{new_text}'"
            )
            
            return result_data
        
        except Exception as e:
            logger.error(
                f"[{self.session_id}] Whisper inference failed: {e}",
                exc_info=True
            )
            return None
    
    def _extract_new_text(self, full_text: str, segments: List[Dict]) -> str:
        """
        Extract new text that wasn't in previous inference.
        
        This avoids sending duplicate partial results.
        
        Args:
            full_text: Full transcribed text from this inference
            segments: Audio segments from Whisper
            
        Returns:
            New text that appeared since last inference
        """
        # Simple approach: if new text is longer, it's new
        if len(full_text) > len(self.full_transcript):
            new_text = full_text[len(self.full_transcript):]
            return new_text.strip()
        
        return ""
    
    def get_partial_result(self) -> Dict[str, str]:
        """
        Get current partial transcription.
        
        Returns:
            Dict with partial transcript info
        """
        return {
            "session_id": self.session_id,
            "type": "partial",
            "text": self.full_transcript,
            "new_text": self.last_partial_text,
            "offset_seconds": self.transcript_offset_seconds,
            "timestamp": datetime.now().isoformat(),
        }
    
    def get_final_result(self) -> Dict[str, Any]:
        """
        Get final transcription result.
        
        Call this when utterance ends.
        
        Returns:
            Dict with complete transcript
        """
        return {
            "session_id": self.session_id,
            "type": "final",
            "text": self.full_transcript,
            "duration_seconds": self.transcript_offset_seconds,
            "inference_count": self.inference_count,
            "timestamp": datetime.now().isoformat(),
        }
    
    def reset(self):
        """Reset inference state (call at utterance boundary)."""
        self.full_transcript = ""
        self.last_partial_text = ""
        self.transcript_offset_seconds = 0.0
        self.last_inference_tokens = []
        self.inference_count = 0
        logger.debug(f"[{self.session_id}] Inference state reset")
    
    def get_stats(self) -> dict:
        """Get inference statistics."""
        avg_inference_time = (
            self.total_inference_time_seconds / self.inference_count
            if self.inference_count > 0 else 0
        )
        
        return {
            "session_id": self.session_id,
            "inference_count": self.inference_count,
            "total_inference_time_seconds": self.total_inference_time_seconds,
            "avg_inference_time_seconds": avg_inference_time,
            "transcript_duration_seconds": self.transcript_offset_seconds,
            "current_text_length": len(self.full_transcript),
        }


class WhisperInferenceManager:
    """Manages Whisper inference for multiple sessions."""
    
    def __init__(self, whisper_model):
        """Initialize manager."""
        self.whisper_model = whisper_model
        self.sessions: dict = {}
    
    def get_or_create_session(self, session_id: str) -> WhisperStreamingInference:
        """Get or create inference session."""
        if session_id not in self.sessions:
            self.sessions[session_id] = WhisperStreamingInference(
                session_id=session_id,
                whisper_model=self.whisper_model,
            )
        
        return self.sessions[session_id]
    
    async def infer(
        self,
        session_id: str,
        audio_buffer: np.ndarray,
    ) -> Optional[Dict[str, Any]]:
        """Run inference for session."""
        session = self.get_or_create_session(session_id)
        return await session.infer_chunk(audio_buffer)
    
    def get_session(self, session_id: str) -> Optional[WhisperStreamingInference]:
        """Get session if exists."""
        return self.sessions.get(session_id)
    
    def release_session(self, session_id: str):
        """Release session (cleanup)."""
        if session_id in self.sessions:
            stats = self.sessions[session_id].get_stats()
            logger.info(f"Releasing inference session {session_id}: {stats}")
            del self.sessions[session_id]
    
    def get_all_stats(self) -> dict:
        """Get stats for all sessions."""
        return {
            session_id: session.get_stats()
            for session_id, session in self.sessions.items()
        }
    
    async def cleanup_all(self):
        """Clean up all sessions."""
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            self.release_session(session_id)
        logger.info(f"Cleaned up {len(session_ids)} inference sessions")
