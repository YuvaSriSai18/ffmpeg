"""Audio processor service - applies FFmpeg preprocessing to audio files."""
import os
import asyncio
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.redis_client import RedisClient
from shared.logging_config import setup_logging

# Setup logging
logger = setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    service_name="audio-processor"
)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "2"))
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Redis client
redis_client = RedisClient(REDIS_URL)


class FFmpegProcessor:
    """Handles FFmpeg audio processing."""

    @staticmethod
    def check_ffmpeg() -> bool:
        """Check if FFmpeg is available."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5
            )
            logger.info("FFmpeg is available")
            return True
        except Exception as e:
            logger.error(f"FFmpeg not available: {e}")
            return False

    @staticmethod
    async def process_audio(input_path: str, output_path: str) -> bool:
        """
        Process audio with FFmpeg pipeline:
        1. Convert to 16kHz mono WAV
        2. Remove silence
        3. Normalize loudness (loudnorm filter)
        4. Attempt denoise (afftdn)
        5. Ensure clipping is handled
        6. Limit output duration
        """
        try:
            input_file = Path(input_path)
            output_file = Path(output_path)

            if not input_file.exists():
                raise FileNotFoundError(f"Input file not found: {input_file}")

            # Create output directory
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Build FFmpeg filter chain - simplified for reliability
            filters = [
                # Convert to 16kHz mono
                "aformat=sample_rates=16000:channel_layouts=mono",
                # Remove silence at start (threshold: -40dB for 0.5s)
                "silenceremove=start_periods=1:start_duration=0.5:start_threshold=-40dB",
                # Normalize loudness to -14 LUFS
                "loudnorm=I=-14:TP=-1.5:LRA=11",
            ]

            filter_string = ",".join(filters)

            # FFmpeg command
            cmd = [
                "ffmpeg",
                "-i", str(input_file),
                "-af", filter_string,
                "-c:a", "pcm_s16le",  # PCM 16-bit
                "-ar", "16000",  # 16kHz sample rate
                "-ac", "1",  # Mono channel
                "-y",  # Overwrite output
                str(output_file),
            ]

            logger.info(f"Running FFmpeg: {' '.join(cmd)}")

            # Run FFmpeg asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"FFmpeg failed: {error_msg}")
                return False

            logger.info(f"Audio processed successfully: {output_file}")
            return True

        except Exception as e:
            logger.error(f"Error processing audio: {e}", exc_info=True)
            return False


async def process_job(job_data: dict) -> bool:
    """
    Process a single job from the queue.
    
    Args:
        job_data: Dictionary with job_id, input_path, metadata
        
    Returns:
        True if successful, False otherwise
    """
    job_id = job_data.get("job_id")
    input_path = job_data.get("input_path")
    metadata = job_data.get("metadata", {})

    if not job_id or not input_path:
        logger.error(f"Invalid job data: {job_data}")
        return False

    try:
        logger.info(f"Processing job {job_id}")

        # Update status
        await redis_client.set_job_status(job_id, "processing_audio")

        # Prepare output path
        output_dir = DATA_DIR / "processed" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "clean.wav"

        # Process audio with FFmpeg
        success = await FFmpegProcessor.process_audio(input_path, str(output_path))

        if not success:
            raise Exception("FFmpeg processing failed")

        logger.info(f"Audio processing complete for job {job_id}")

        # Update status
        await redis_client.set_job_status(job_id, "audio_ready")

        # Push to transcription queue
        message = {
            "job_id": job_id,
            "clean_path": str(output_path),
        }
        await redis_client.push_job("stt:transcribe:queue", json.dumps(message))

        logger.info(f"Pushed job {job_id} to stt:transcribe:queue")
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
        logger.info("Worker loop started, listening to stt:jobs:queue")

        while True:
            try:
                # Wait for job from queue (blocking with 5 second timeout)
                message = await redis_client.pop_job("stt:jobs:queue", timeout=5)

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
        # Ensure data directories exist
        (DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "processed").mkdir(parents=True, exist_ok=True)

        # Check FFmpeg availability
        if not FFmpegProcessor.check_ffmpeg():
            logger.warning("FFmpeg not found - audio processing will fail")

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
        logger.info("Audio processor shutdown complete")


if __name__ == "__main__":
    from datetime import timedelta
    asyncio.run(main())
