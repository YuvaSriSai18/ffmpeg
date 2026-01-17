"""Voice Activity Detection (VAD) module using Silero VAD.

Stream-based VAD that:
- Detects speech vs silence in real-time
- Tracks end-of-utterance (silence > 500-800ms)
- Maintains per-session state
- Operates on raw PCM frames (16kHz, 16-bit, mono)
"""

import logging
from typing import Tuple, Optional
import numpy as np
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)


class SileroVAD:
    """
    Silero VAD wrapper for streaming speech detection.
    
    Maintains state across frames to detect:
    - Speech/silence transitions
    - End-of-utterance (continued silence)
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 20,
        silence_threshold_ms: int = 500,
    ):
        """
        Initialize Silero VAD.
        
        Args:
            sample_rate: Audio sample rate (Hz)
            frame_duration_ms: Frame size in milliseconds
            silence_threshold_ms: Silence duration to trigger end-of-utterance
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.silence_threshold_ms = silence_threshold_ms
        
        # Frame size in samples
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        
        # Silence counter (in frames)
        self.silence_frames_threshold = int(
            silence_threshold_ms / frame_duration_ms
        )
        
        # State tracking
        self.is_speech = False
        self.silence_frame_count = 0
        self.last_speech_time = None
        
        # Try to load Silero VAD model
        try:
            self.model = self._load_model()
            self.model_ready = True
            logger.info(
                f"Silero VAD loaded (frame_duration={frame_duration_ms}ms, "
                f"silence_threshold={silence_threshold_ms}ms)"
            )
        except Exception as e:
            logger.warning(
                f"Silero VAD not available, using fallback RMS-based detection: {e}"
            )
            self.model = None
            self.model_ready = False
    
    def _load_model(self):
        """Load Silero VAD model (ONNX runtime)."""
        try:
            import onnxruntime as rt
            # Use CPU provider for compatibility
            providers = ['CPUExecutionProvider']
            
            # Load Silero VAD model from HuggingFace hub
            # For production, consider downloading and caching locally
            model_name = "silero_vad"
            model_path = f"models/{model_name}.onnx"
            
            session = rt.InferenceSession(model_path, providers=providers)
            return session
        except ImportError:
            logger.warning("onnxruntime not installed, using RMS fallback")
            return None
        except Exception as e:
            logger.warning(f"Could not load Silero VAD ONNX model: {e}")
            return None
    
    def process_frame(
        self,
        audio_frame: np.ndarray,
    ) -> Tuple[bool, bool, float]:
        """
        Process a single audio frame for VAD.
        
        Args:
            audio_frame: PCM audio frame (16-bit, mono, 16kHz)
            
        Returns:
            Tuple of:
            - is_speech: True if frame contains speech
            - utterance_end: True if end-of-utterance detected
            - confidence: Speech confidence (0.0-1.0)
        """
        # Validate frame size
        if len(audio_frame) != self.frame_size:
            logger.warning(
                f"Frame size mismatch: expected {self.frame_size}, "
                f"got {len(audio_frame)}"
            )
            # Pad or truncate frame
            if len(audio_frame) < self.frame_size:
                audio_frame = np.pad(
                    audio_frame,
                    (0, self.frame_size - len(audio_frame))
                )
            else:
                audio_frame = audio_frame[:self.frame_size]
        
        # Detect speech
        if self.model_ready:
            is_speech, confidence = self._detect_with_silero(audio_frame)
        else:
            is_speech, confidence = self._detect_with_rms(audio_frame)
        
        # Track utterance end
        utterance_end = False
        
        if is_speech:
            self.is_speech = True
            self.silence_frame_count = 0
            self.last_speech_time = datetime.now()
        else:
            # Increment silence counter
            self.silence_frame_count += 1
            
            # Detect end-of-utterance
            if (self.is_speech and 
                self.silence_frame_count >= self.silence_frames_threshold):
                utterance_end = True
                self.is_speech = False
                logger.debug(
                    f"End-of-utterance detected after "
                    f"{self.silence_frame_count * self.frame_duration_ms}ms "
                    f"of silence"
                )
        
        return is_speech, utterance_end, confidence
    
    def _detect_with_silero(
        self,
        audio_frame: np.ndarray
    ) -> Tuple[bool, float]:
        """
        Detect speech using Silero VAD model.
        
        Args:
            audio_frame: Audio frame as numpy array
            
        Returns:
            Tuple of (is_speech, confidence)
        """
        try:
            # Normalize audio to [-1, 1]
            audio_frame = audio_frame.astype(np.float32) / 32768.0
            
            # Silero VAD expects input shape (batch, samples)
            input_data = audio_frame.reshape(1, -1)
            
            # Run model
            outputs = self.model.run(
                None,
                {"input": input_data}
            )
            
            # Output is speech probability
            confidence = float(outputs[0][0][0])
            is_speech = confidence > 0.5
            
            return is_speech, confidence
        except Exception as e:
            logger.warning(f"Silero VAD inference failed: {e}, using RMS fallback")
            return self._detect_with_rms(audio_frame)
    
    def _detect_with_rms(
        self,
        audio_frame: np.ndarray
    ) -> Tuple[bool, float]:
        """
        Fallback speech detection using RMS energy.
        
        Simple heuristic when Silero VAD unavailable:
        - High RMS = likely speech
        - Low RMS = likely silence
        
        Args:
            audio_frame: Audio frame as numpy array
            
        Returns:
            Tuple of (is_speech, confidence)
        """
        # Convert to float
        audio_float = audio_frame.astype(np.float32) / 32768.0
        
        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio_float ** 2))
        
        # Threshold (tuned for typical speech)
        # Typical silence: RMS < 0.01
        # Typical speech: RMS > 0.05
        threshold = 0.03
        
        is_speech = rms > threshold
        
        # Normalize RMS to confidence (0-1 range)
        # RMS 0.01 -> confidence 0.0
        # RMS 0.1 -> confidence 1.0
        confidence = min(1.0, max(0.0, (rms - 0.01) / 0.09))
        
        return is_speech, confidence
    
    def reset(self):
        """Reset VAD state (call when session ends)."""
        self.is_speech = False
        self.silence_frame_count = 0
        self.last_speech_time = None
        logger.debug("VAD state reset")


class VADSession:
    """Manages VAD state for a single streaming session."""
    
    def __init__(
        self,
        session_id: str,
        sample_rate: int = 16000,
        frame_duration_ms: int = 20,
        silence_threshold_ms: int = 500,
    ):
        """Initialize VAD session."""
        self.session_id = session_id
        self.vad = SileroVAD(
            sample_rate=sample_rate,
            frame_duration_ms=frame_duration_ms,
            silence_threshold_ms=silence_threshold_ms,
        )
        self.voiced_frames = 0
        self.total_frames = 0
    
    def process_frame(self, audio_frame: np.ndarray):
        """
        Process frame and return VAD results.
        
        Returns:
            Dict with detection results
        """
        is_speech, utterance_end, confidence = self.vad.process_frame(audio_frame)
        
        self.total_frames += 1
        if is_speech:
            self.voiced_frames += 1
        
        return {
            "is_speech": is_speech,
            "utterance_end": utterance_end,
            "confidence": confidence,
            "voiced_frames": self.voiced_frames,
            "total_frames": self.total_frames,
        }
    
    def get_stats(self) -> dict:
        """Get VAD statistics for this session."""
        speech_ratio = (
            self.voiced_frames / self.total_frames
            if self.total_frames > 0 else 0
        )
        
        return {
            "total_frames": self.total_frames,
            "voiced_frames": self.voiced_frames,
            "silence_frames": self.total_frames - self.voiced_frames,
            "speech_ratio": speech_ratio,
        }
    
    def reset(self):
        """Reset session."""
        self.vad.reset()
        self.voiced_frames = 0
        self.total_frames = 0
