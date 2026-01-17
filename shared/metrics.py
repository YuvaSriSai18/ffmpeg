"""Latency metrics collection for streaming audio processing.

Tracks per-stage timing:
- Audio receive time
- VAD processing time
- FFmpeg processing time
- Whisper inference time
- Event emission time

Computes end-to-end latency metrics.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import time

logger = logging.getLogger(__name__)


class LatencyTracker:
    """Tracks latency for a single session."""
    
    def __init__(self, session_id: str):
        """Initialize tracker."""
        self.session_id = session_id
        
        # Stage timestamps (milliseconds)
        self.stages: Dict[str, float] = {}
        
        # Per-stage durations
        self.stage_durations: Dict[str, list] = defaultdict(list)
        
        # Utterance timings
        self.utterance_start_time: Optional[float] = None
        self.utterance_end_time: Optional[float] = None
        
        # Statistics
        self.total_utterances = 0
        self.total_chunks = 0
        self.total_inferences = 0
    
    def mark_stage(self, stage_name: str):
        """Mark timestamp for a processing stage."""
        self.stages[stage_name] = time.time() * 1000  # milliseconds
    
    def record_stage_duration(self, stage_name: str, duration_ms: float):
        """Record duration for a stage."""
        self.stage_durations[stage_name].append(duration_ms)
    
    def get_stage_duration_ms(
        self,
        stage_start: str,
        stage_end: str
    ) -> Optional[float]:
        """
        Get duration between two stages in milliseconds.
        
        Args:
            stage_start: Start stage name
            stage_end: End stage name
            
        Returns:
            Duration in milliseconds, or None if stages not marked
        """
        if stage_start not in self.stages or stage_end not in self.stages:
            return None
        
        return self.stages[stage_end] - self.stages[stage_start]
    
    def mark_utterance_start(self):
        """Mark start of utterance."""
        self.utterance_start_time = time.time() * 1000
    
    def mark_utterance_end(self):
        """Mark end of utterance."""
        self.utterance_end_time = time.time() * 1000
        if self.utterance_start_time is not None:
            self.total_utterances += 1
    
    def get_utterance_duration_ms(self) -> Optional[float]:
        """Get total utterance duration."""
        if (self.utterance_start_time is None or 
            self.utterance_end_time is None):
            return None
        
        return self.utterance_end_time - self.utterance_start_time
    
    def get_stage_stats(self, stage_name: str) -> Dict[str, float]:
        """Get statistics for a stage."""
        durations = self.stage_durations[stage_name]
        
        if not durations:
            return {
                "count": 0,
                "total_ms": 0.0,
                "avg_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
            }
        
        return {
            "count": len(durations),
            "total_ms": sum(durations),
            "avg_ms": sum(durations) / len(durations),
            "min_ms": min(durations),
            "max_ms": max(durations),
        }
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get comprehensive latency statistics."""
        stats = {
            "session_id": self.session_id,
            "total_utterances": self.total_utterances,
            "total_chunks": self.total_chunks,
            "total_inferences": self.total_inferences,
            "stages": {},
        }
        
        # Add stage statistics
        for stage_name in self.stage_durations.keys():
            stats["stages"][stage_name] = self.get_stage_stats(stage_name)
        
        return stats


class MetricsCollector:
    """Collects metrics for all sessions."""
    
    def __init__(self):
        """Initialize collector."""
        self.trackers: Dict[str, LatencyTracker] = {}
    
    def get_or_create_tracker(self, session_id: str) -> LatencyTracker:
        """Get or create tracker for session."""
        if session_id not in self.trackers:
            self.trackers[session_id] = LatencyTracker(session_id)
        
        return self.trackers[session_id]
    
    def record_stage(self, session_id: str, stage_name: str):
        """Record stage timestamp."""
        tracker = self.get_or_create_tracker(session_id)
        tracker.mark_stage(stage_name)
    
    def record_stage_duration(
        self,
        session_id: str,
        stage_name: str,
        duration_ms: float,
    ):
        """Record stage duration."""
        tracker = self.get_or_create_tracker(session_id)
        tracker.record_stage_duration(stage_name, duration_ms)
    
    def get_duration(
        self,
        session_id: str,
        stage_start: str,
        stage_end: str,
    ) -> Optional[float]:
        """Get duration between stages."""
        if session_id not in self.trackers:
            return None
        
        tracker = self.trackers[session_id]
        return tracker.get_stage_duration_ms(stage_start, stage_end)
    
    def release_session(self, session_id: str):
        """Release session and log final metrics."""
        if session_id in self.trackers:
            tracker = self.trackers[session_id]
            stats = tracker.get_all_stats()
            logger.info(
                f"Session {session_id} final metrics: {stats}"
            )
            del self.trackers[session_id]
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get stats for all sessions."""
        return {
            session_id: tracker.get_all_stats()
            for session_id, tracker in self.trackers.items()
        }
    
    async def cleanup_all(self):
        """Clean up all trackers."""
        session_ids = list(self.trackers.keys())
        for session_id in session_ids:
            self.release_session(session_id)


class LatencyContext:
    """Context manager for measuring latency of a code block."""
    
    def __init__(
        self,
        collector: MetricsCollector,
        session_id: str,
        stage_name: str,
    ):
        """Initialize context."""
        self.collector = collector
        self.session_id = session_id
        self.stage_name = stage_name
        self.start_time: Optional[float] = None
    
    def __enter__(self):
        """Enter context (start timing)."""
        self.start_time = time.time() * 1000
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context (record duration)."""
        if self.start_time is not None:
            duration_ms = (time.time() * 1000) - self.start_time
            self.collector.record_stage_duration(
                self.session_id,
                self.stage_name,
                duration_ms,
            )
            logger.debug(
                f"[{self.session_id}] {self.stage_name}: {duration_ms:.2f}ms"
            )


def log_latency_summary(metrics: Dict[str, Any]):
    """
    Log summary of latency metrics.
    
    Args:
        metrics: Metrics dictionary from MetricsCollector
    """
    logger.info("=== Latency Metrics Summary ===")
    
    for session_id, stats in metrics.items():
        logger.info(f"\nSession: {session_id}")
        logger.info(f"  Total utterances: {stats['total_utterances']}")
        logger.info(f"  Total chunks: {stats['total_chunks']}")
        logger.info(f"  Total inferences: {stats['total_inferences']}")
        
        logger.info("  Stage timings (avg ms):")
        for stage_name, stage_stats in stats["stages"].items():
            if stage_stats["count"] > 0:
                logger.info(
                    f"    {stage_name}: "
                    f"avg={stage_stats['avg_ms']:.2f}ms, "
                    f"min={stage_stats['min_ms']:.2f}ms, "
                    f"max={stage_stats['max_ms']:.2f}ms"
                )
