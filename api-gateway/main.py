"""API Gateway service for STT transcription."""
import os
import uuid
import logging
import json
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, Response, status
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio

# Import shared modules
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.models import (
    JobUploadResponse,
    JobStatusRequest,
    JobStatus,
    JobMetadata,
    ProcessingMessage,
)
from shared.redis_client import RedisClient
from shared.logging_config import setup_logging

# Setup logging
logger = setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    service_name="api-gateway"
)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "100")) * 1024 * 1024  # 100MB default
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}

# Redis client
redis_client = RedisClient(REDIS_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    logger.info("Starting API Gateway service")
    await redis_client.connect()
    yield
    # Shutdown
    logger.info("Shutting down API Gateway service")
    await redis_client.disconnect()


app = FastAPI(
    title="STT API Gateway",
    description="Accept audio uploads and manage transcription jobs",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Try to ping Redis
        await redis_client.client.ping()
        return {
            "status": "healthy",
            "service": "api-gateway",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": "api-gateway",
                "error": str(e),
            },
        )


@app.post("/v1/stt/jobs", response_model=JobUploadResponse)
async def create_job(file: UploadFile = File(...)):
    """
    Upload audio file and create transcription job.
    
    Returns:
        JobUploadResponse with job_id and status_url
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Filename is required"
            )

        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type {file_ext} not allowed. Allowed: {ALLOWED_EXTENSIONS}"
            )

        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Create upload directory
        upload_dir = DATA_DIR / "uploads" / job_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Read and save file
        contents = await file.read()
        
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max {MAX_FILE_SIZE / (1024*1024):.0f}MB"
            )
        
        input_path = upload_dir / f"input{file_ext}"
        input_path.write_bytes(contents)
        
        logger.info(f"File saved for job {job_id}: {input_path}")
        
        # Create metadata
        metadata = {
            "original_filename": file.filename,
            "file_size": len(contents),
            "content_type": file.content_type,
            "uploaded_at": datetime.utcnow().isoformat(),
        }
        
        # Store metadata in Redis
        await redis_client.set_job_metadata(job_id, metadata)
        
        # Set initial status
        await redis_client.set_job_status(job_id, "uploaded")
        
        # Publish to processing queue
        message = {
            "job_id": job_id,
            "input_path": str(input_path),
            "metadata": metadata,
        }
        await redis_client.push_job("stt:jobs:queue", json.dumps(message))
        
        logger.info(f"Job created: {job_id}, pushed to stt:jobs:queue")
        
        return JobUploadResponse(
            job_id=job_id,
            status_url=f"/v1/stt/jobs/{job_id}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating job: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process upload: {str(e)}"
        )


@app.get("/v1/stt/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """
    Get status and result of a transcription job.
    
    Returns:
        JobStatus with current status, metadata, and result if available
    """
    try:
        # Check if job exists
        if not await redis_client.exists(f"stt:jobs:{job_id}:status"):
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found"
            )
        
        # Get status
        status = await redis_client.get_job_status(job_id)
        
        # Get metadata
        metadata_dict = await redis_client.get_job_metadata(job_id)
        metadata = None
        if metadata_dict:
            metadata = JobMetadata(
                original_filename=metadata_dict.get("original_filename", ""),
                file_size=metadata_dict.get("file_size", 0),
                content_type=metadata_dict.get("content_type", ""),
                uploaded_at=datetime.fromisoformat(metadata_dict.get("uploaded_at", datetime.utcnow().isoformat()))
            )
        
        # Get result if available
        result_dict = await redis_client.get_job_result(job_id)
        result = None
        if result_dict:
            # Parse result back to model
            from shared.models import AudioSegment, TranscriptionResult
            segments = [
                AudioSegment(**seg) if isinstance(seg, dict) else seg
                for seg in result_dict.get("segments", [])
            ]
            result = TranscriptionResult(
                job_id=result_dict.get("job_id", job_id),
                text=result_dict.get("text", ""),
                language=result_dict.get("language", "en"),
                segments=segments,
                duration=result_dict.get("duration", 0.0),
                transcribed_at=datetime.fromisoformat(result_dict.get("transcribed_at", datetime.utcnow().isoformat()))
            )
        
        logger.info(f"Retrieved status for job {job_id}: {status}")
        
        return JobStatus(
            job_id=job_id,
            status=status,
            metadata=metadata,
            result=result,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving job status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve job status: {str(e)}"
        )


@app.get("/")
async def root():
    """Root endpoint with API documentation."""
    return {
        "service": "STT API Gateway",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "upload": "POST /v1/stt/jobs",
            "status": "GET /v1/stt/jobs/{job_id}",
            "health": "GET /health",
        }
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT") != "production",
    )
