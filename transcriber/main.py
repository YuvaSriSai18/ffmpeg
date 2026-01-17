"""Transcriber service - uses Whisper to transcribe audio."""
import os
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.redis_client import RedisClient
from shared.logging_config import setup_logging
from shared.vad import VADSession
from shared.buffer_manager import BufferManager
from shared.ffmpeg_pipeline import FFmpegManager
from shared.whisper_streaming import WhisperInferenceManager
from shared.metrics import MetricsCollector, log_latency_summary
from shared.streaming_processor import StreamingAudioProcessor

# Setup logging
logger = setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    service_name="transcriber"
)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "1"))
STREAMING_WORKERS = int(os.getenv("STREAMING_WORKERS", "1"))
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Redis client
redis_client = RedisClient(REDIS_URL)

# Global whisper model (loaded once)
whisper_model = None

# Managers for streaming
buffer_manager = None
ffmpeg_manager = None
whisper_manager = None
metrics_collector = None

# Active processors per session
processors: Dict[str, StreamingAudioProcessor] = {}


def load_whisper_model():
    """Load Whisper model (do this once to save memory)."""
    global whisper_model
    try:
        import whisper
        logger.info(f"Loading Whisper model: {WHISPER_MODEL}")
        whisper_model = whisper.load_model(WHISPER_MODEL)
        logger.info(f"Whisper model loaded successfully")
        return True
    except ImportError:
        logger.error("Whisper not installed, trying faster-whisper...")
        return False
    except Exception as e:
        logger.error(f"Error loading Whisper model: {e}", exc_info=True)
        return False


async def initialize_managers():
    """Initialize all streaming managers."""
    global buffer_manager, ffmpeg_manager, whisper_manager, metrics_collector
    
    try:
        buffer_manager = BufferManager(default_max_duration=5.0)
        ffmpeg_manager = FFmpegManager()
        whisper_manager = WhisperInferenceManager(whisper_model)
        metrics_collector = MetricsCollector()
        
        logger.info("All streaming managers initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize managers: {e}", exc_info=True)
        return False


async def handle_stream_audio_chunk(
    session_id: str,
    chunk_bytes: bytes,
) -> Dict[str, Any]:
    """
    Handle incoming streaming audio chunk.
    
    Args:
        session_id: Session identifier
        chunk_bytes: Raw PCM audio chunk
        
    Returns:
        Processing result
    """
    # Get or create processor for this session
    if session_id not in processors:
        processor = StreamingAudioProcessor(
            session_id=session_id,
            buffer_manager=buffer_manager,
            ffmpeg_manager=ffmpeg_manager,
            vad_manager=type('obj', (object,), {
                'get_or_create_session': lambda self, sid: VADSession(sid)
            })(),
            whisper_manager=whisper_manager,
            metrics_collector=metrics_collector,
            redis_client=redis_client,
        )
        
        # Start session
        success = await processor.start_session()
        if not success:
            logger.error(f"Failed to start processor for {session_id}")
            return {"success": False, "error": "Failed to start session"}
        
        processors[session_id] = processor
    
    # Process chunk
    processor = processors[session_id]
    result = await processor.process_audio_chunk(chunk_bytes)
    
    return result


async def streaming_transcribe_worker():
    """
    Worker loop for streaming transcription.
    
    Listens for streaming audio chunks and processes them in real-time.
    """
    logger.info("Streaming transcription worker started")
    
    try:
        while True:
            try:
                # Listen for streaming audio chunks
                # Format: {"session_id": "...", "chunk": "base64..."}
                message = await redis_client.pop_job(
                    "stt:stream:audio:queue",
                    timeout=5
                )
                
                if not message:
                    continue
                
                try:
                    data = json.loads(message)
                    session_id = data.get("session_id")
                    chunk_base64 = data.get("chunk")
                    
                    if not session_id or not chunk_base64:
                        logger.warning(f"Invalid message format: {data}")
                        continue
                    
                    # Decode chunk
                    import base64
                    chunk_bytes = base64.b64decode(chunk_base64)
                    
                    # Process chunk
                    result = await handle_stream_audio_chunk(session_id, chunk_bytes)
                    
                    # Log result events
                    for event in result.get("events", []):
                        logger.debug(f"Event: {event}")
                
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message: {e}")
                except Exception as e:
                    logger.error(f"Error processing stream chunk: {e}", exc_info=True)
            
            except Exception as e:
                logger.error(f"Error in streaming worker: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Streaming worker interrupted")


async def transcribe_audio(audio_path: str) -> Optional[Dict[str, Any]]:
    """
    Transcribe audio file using Whisper.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        Dictionary with transcription result or None if failed
    """
    try:
        global whisper_model
        
        if whisper_model is None:
            logger.error("Whisper model not loaded")
            return None

        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        logger.info(f"Transcribing: {audio_file}")

        # Run transcription in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: whisper_model.transcribe(
                str(audio_file),
                language="en",
                verbose=False,
            )
        )

        # Transform result
        transcription = {
            "text": result.get("text", "").strip(),
            "language": result.get("language", "en"),
            "duration": result.get("duration", 0.0),
            "segments": [
                {
                    "id": seg.get("id", 0),
                    "seek": seg.get("seek", 0),
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "text": seg.get("text", "").strip(),
                    "tokens": seg.get("tokens", []),
                    "temperature": seg.get("temperature", 0.0),
                    "avg_logprob": seg.get("avg_logprob", 0.0),
                    "compression_ratio": seg.get("compression_ratio", 0.0),
                    "no_speech_prob": seg.get("no_speech_prob", 0.0),
                }
                for seg in result.get("segments", [])
            ],
        }

        logger.info(f"Transcription complete, text length: {len(transcription['text'])}")
        return transcription

    except Exception as e:
        logger.error(f"Error transcribing audio: {e}", exc_info=True)
        return None


async def transcribe_and_stream(
    audio_path: str,
    job_id: str,
    redis_client
) -> Optional[Dict[str, Any]]:
    """
    Transcribe audio and stream results in real-time.
    
    WHY: Stream segments as they are transcribed
    User sees transcription appearing word-by-word (better UX)
    Instead of waiting for entire transcription to complete.
    
    Args:
        audio_path: Path to preprocessed audio file
        job_id: Unique job identifier for publishing results
        redis_client: Redis client for publishing
        
    Returns:
        Full transcription dictionary or None if failed
    """
    try:
        global whisper_model
        
        if whisper_model is None:
            logger.error("Whisper model not loaded")
            return None
        
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")
        
        logger.info(f"Transcribing with streaming for job {job_id}: {audio_file}")
        
        # Notify that transcription is starting
        await redis_client.publish_stream_status(
            job_id,
            "transcribing",
            {"file": str(audio_file)}
        )
        
        # Run transcription in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: whisper_model.transcribe(
                str(audio_file),
                language="en",
                verbose=False,
            )
        )
        
        # WHY: Publish each segment in real-time
        # Don't wait for full transcription - send as you get results
        segments = result.get("segments", [])
        logger.info(f"Transcription generated {len(segments)} segments")
        
        for segment in segments:
            text = segment.get("text", "").strip()
            start = segment.get("start", 0.0)
            end = segment.get("end", 0.0)
            
            if text:
                # Publish segment immediately
                await redis_client.publish_transcript_chunk(
                    job_id=job_id,
                    text=text,
                    start_time=start,
                    end_time=end,
                    confidence=0.95
                )
                logger.info(
                    f"Published segment [{start:.2f}s-{end:.2f}s]: {text}"
                )
        
        # Transform result
        transcription = {
            "text": result.get("text", "").strip(),
            "language": result.get("language", "en"),
            "duration": result.get("duration", 0.0),
            "segments": [
                {
                    "id": seg.get("id", 0),
                    "seek": seg.get("seek", 0),
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "text": seg.get("text", "").strip(),
                    "tokens": seg.get("tokens", []),
                    "temperature": seg.get("temperature", 0.0),
                    "avg_logprob": seg.get("avg_logprob", 0.0),
                    "compression_ratio": seg.get("compression_ratio", 0.0),
                    "no_speech_prob": seg.get("no_speech_prob", 0.0),
                }
                for seg in result.get("segments", [])
            ],
        }
        
        logger.info(
            f"Streaming transcription complete for {job_id}, "
            f"text length: {len(transcription['text'])}"
        )
        
        return transcription
    
    except Exception as e:
        logger.error(
            f"Error in streaming transcription for {job_id}: {e}",
            exc_info=True
        )
        await redis_client.publish_stream_status(
            job_id,
            "transcription_failed",
            {"error": str(e)}
        )
        return None


async def process_job(job_data: dict) -> bool:
    """
    Process a single transcription job.
    
    Args:
        job_data: Dictionary with job_id and clean_path
        
    Returns:
        True if successful, False otherwise
    """
    job_id = job_data.get("job_id")
    clean_path = job_data.get("clean_path")

    if not job_id or not clean_path:
        logger.error(f"Invalid job data: {job_data}")
        return False

    try:
        logger.info(f"Transcribing job {job_id}")

        # Update status
        await redis_client.set_job_status(job_id, "transcribing")

        # Transcribe audio
        result = await transcribe_audio(clean_path)

        if result is None:
            raise Exception("Transcription failed")

        # Store result in Redis
        result_with_id = {
            "job_id": job_id,
            "transcribed_at": datetime.utcnow().isoformat(),
            **result
        }
        await redis_client.set_job_result(job_id, result_with_id)

        logger.info(f"Transcription saved for job {job_id}")

        # Update final status
        await redis_client.set_job_status(job_id, "completed")

        logger.info(f"Job {job_id} completed successfully")
        return True

    except Exception as e:
        logger.error(f"Error processing job {job_id}: {e}", exc_info=True)
        await redis_client.set_job_status(job_id, "failed")
        return False


async def worker_loop():
    """
    Main worker loop - listens to Redis queue and processes jobs.
    Implements graceful shutdown and retry logic.
    """
    retries_remaining = MAX_RETRIES

    try:
        logger.info("Worker loop started, listening to stt:transcribe:queue")

        while True:
            try:
                # Wait for job from queue (blocking with 5 second timeout)
                message = await redis_client.pop_job("stt:transcribe:queue", timeout=5)

                if message:
                    try:
                        job_data = json.loads(message)
                        job_id = job_data.get("job_id")
                        
                        logger.info(f"Received job {job_id} from queue")

                        # Process with retries
                        success = False
                        for attempt in range(MAX_RETRIES):
                            success = await process_job(job_data)
                            if success:
                                retries_remaining = MAX_RETRIES
                                break
                            if attempt < MAX_RETRIES - 1:
                                logger.warning(f"Job {job_id} attempt {attempt + 1} failed, retrying...")
                                await asyncio.sleep(RETRY_DELAY)

                        if not success:
                            logger.error(f"Job {job_id} failed after {MAX_RETRIES} retries")
                            await redis_client.set_job_status(job_id, "failed")

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse message: {e}")
                    except Exception as e:
                        logger.error(f"Error in job processing: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                retries_remaining -= 1
                if retries_remaining <= 0:
                    logger.error("Max retries reached, exiting worker loop")
                    break
                await asyncio.sleep(RETRY_DELAY)
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error in worker: {e}", exc_info=True)
    finally:
        logger.info("Worker loop ended")


async def streaming_worker_loop() -> None:
    """
    Worker loop for streaming transcription jobs.
    
    WHY: Separate worker for real-time streaming
    Handles WebSocket audio that arrives in chunks
    Transcribes with immediate results (streaming mode)
    """
    logger.info("Streaming worker loop started")
    
    try:
        while True:
            try:
                # Listen for streaming transcription requests
                # These come from Audio Processor after preprocessing
                message = await redis_client.pop_job(
                    "stt:transcribe:stream",
                    timeout=5
                )
                
                if message:
                    try:
                        job_data = json.loads(message)
                        job_id = job_data.get("job_id")
                        audio_path = job_data.get("audio_path")
                        
                        logger.info(
                            f"Received streaming job {job_id}: {audio_path}"
                        )
                        
                        # Transcribe with streaming results
                        result = await transcribe_and_stream(
                            audio_path,
                            job_id,
                            redis_client
                        )
                        
                        if result is None:
                            logger.error(f"Streaming transcription failed for {job_id}")
                            await redis_client.publish_stream_status(
                                job_id,
                                "transcription_failed"
                            )
                            await redis_client.set_job_status(job_id, "failed")
                        else:
                            # Store final result
                            result_with_id = {
                                "job_id": job_id,
                                "transcribed_at": datetime.utcnow().isoformat(),
                                **result
                            }
                            await redis_client.set_job_result(job_id, result_with_id)
                            
                            logger.info(
                                f"Streaming job {job_id} completed successfully"
                            )
                            
                            # Notify completion
                            await redis_client.publish_stream_status(
                                job_id,
                                "completed"
                            )
                            await redis_client.set_job_status(
                                job_id,
                                "completed"
                            )
                    
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse streaming message: {e}")
                    except Exception as e:
                        logger.error(
                            f"Error in streaming job processing: {e}",
                            exc_info=True
                        )
            
            except Exception as e:
                logger.error(f"Error in streaming worker loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Streaming worker loop interrupted")


async def start_workers():
    """
    Start multiple worker tasks for concurrent processing.
    
    Runs both batch and streaming workers:
    - Batch: Handle regular file uploads (stt:transcribe:queue)
    - Streaming: Handle WebSocket real-time transcription (stt:stream:audio:queue)
    """
    tasks = [
        # Batch transcription workers (file-based)
        asyncio.create_task(worker_loop())
        for _ in range(WORKER_CONCURRENCY)
    ]
    
    # Add streaming workers (real-time audio chunks)
    if STREAMING_WORKERS > 0:
        logger.info(f"Starting {STREAMING_WORKERS} streaming worker(s)")
        tasks.extend([
            asyncio.create_task(streaming_transcribe_worker())
            for _ in range(STREAMING_WORKERS)
        ])
    
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Stopping all workers...")
        
        # Cancel all tasks
        for task in tasks:
            task.cancel()
        
        # Wait for cancellation
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Cleanup streaming sessions
        logger.info("Cleaning up streaming sessions...")
        for session_id, processor in list(processors.items()):
            await processor.stop_session()
        
        # Cleanup managers
        if ffmpeg_manager:
            await ffmpeg_manager.cleanup_all()
        if whisper_manager:
            await whisper_manager.cleanup_all()
        if metrics_collector:
            await metrics_collector.cleanup_all()
            # Log final metrics
            stats = metrics_collector.get_all_stats()
            if stats:
                log_latency_summary(stats)


async def main():
    """Main entry point."""
    try:
        # Load Whisper model
        if not load_whisper_model():
            logger.error("Failed to load Whisper model, exiting")
            return

        # Connect to Redis
        await redis_client.connect()

        # Initialize streaming managers
        if not await initialize_managers():
            logger.error("Failed to initialize managers, exiting")
            return

        logger.info(
            f"Starting {WORKER_CONCURRENCY} batch worker(s) "
            f"and {STREAMING_WORKERS} streaming worker(s)"
        )
        
        # Start worker tasks
        await start_workers()

    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
    finally:
        await redis_client.disconnect()
        logger.info("Transcriber shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
