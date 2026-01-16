"""Transcriber service - uses Whisper to transcribe audio."""
import os
import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, Any

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.redis_client import RedisClient
from shared.logging_config import setup_logging

# Setup logging
logger = setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    service_name="transcriber"
)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "1"))
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Redis client
redis_client = RedisClient(REDIS_URL)

# Global whisper model (loaded once)
whisper_model = None


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


async def start_workers():
    """Start multiple worker tasks for concurrent processing."""
    tasks = [
        asyncio.create_task(worker_loop())
        for _ in range(WORKER_CONCURRENCY)
    ]
    
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Stopping all workers...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def main():
    """Main entry point."""
    try:
        # Load Whisper model
        if not load_whisper_model():
            logger.error("Failed to load Whisper model, exiting")
            return

        # Connect to Redis
        await redis_client.connect()

        logger.info(f"Starting {WORKER_CONCURRENCY} worker(s)")
        
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
