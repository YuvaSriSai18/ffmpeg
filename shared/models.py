"""Shared Pydantic models for message passing and responses."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import json


class JobMetadata(BaseModel):
    """Metadata for a transcription job."""
    original_filename: str
    file_size: int
    content_type: str
    uploaded_at: datetime


class JobStatusRequest(BaseModel):
    """Request to publish a new job."""
    job_id: str
    input_path: str
    metadata: JobMetadata

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AudioSegment(BaseModel):
    """A segment of transcribed audio with timing."""
    id: int
    seek: int
    start: float
    end: float
    text: str
    tokens: List[int]
    temperature: float
    avg_logprob: float
    compression_ratio: float
    no_speech_prob: float


class TranscriptionResult(BaseModel):
    """Result of audio transcription."""
    job_id: str
    text: str
    language: str = "en"
    segments: List[AudioSegment] = []
    duration: float = 0.0
    transcribed_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class JobStatus(BaseModel):
    """Current status of a transcription job."""
    job_id: str
    status: str  # uploaded, processing_audio, audio_ready, transcribing, completed, failed
    metadata: Optional[JobMetadata] = None
    result: Optional[TranscriptionResult] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class JobUploadResponse(BaseModel):
    """Response after uploading audio file."""
    job_id: str
    status_url: str


class ProcessingMessage(BaseModel):
    """Message for audio processing queue."""
    job_id: str
    input_path: str
    metadata: Optional[Dict[str, Any]] = None


class TranscribeMessage(BaseModel):
    """Message for transcription queue."""
    job_id: str
    clean_path: str
