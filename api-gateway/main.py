"""API Gateway service for STT transcription."""
import os
import uuid
import json
import base64
import asyncio
import time
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager

# Import shared modules
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.models import (
    JobUploadResponse,
    JobStatus,
    JobMetadata,
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
            "stream": "WS /v1/stt/stream",
            "ws_test": "GET /ws-test"
        }
    }


# ==================== WebSocket Streaming Endpoints ====================

@app.websocket("/v1/stt/stream")
async def websocket_streaming_transcription(websocket: WebSocket):
    """
    WebSocket endpoint for real-time streaming transcription.
    
    WHY WebSocket?
    - Persistent connection (no reconnect overhead)
    - Real-time bidirectional communication
    - Efficient: single connection for entire transcription
    - Live feedback: user sees transcription appearing in real-time
    
    Protocol:
    Client → Server:
        {"type": "start", "format": "wav", "sample_rate": 16000}
        {"type": "audio", "data": "base64_chunk", "index": 0}
        {"type": "audio", "data": "base64_chunk", "index": 1}
        ...
        {"type": "end"}
    
    Server → Client:
        {"type": "connected", "job_id": "xxx", "message": "Ready"}
        {"type": "status", "status": "receiving", "message": "..."}
        {"type": "transcript", "text": "The quick brown", "start": 0.0, "end": 1.5}
        {"type": "transcript", "text": "fox jumps over", "start": 1.5, "end": 3.0}
        {"type": "status", "status": "completed"}
        {"type": "result", "text": "Full transcription...", "segments": [...]}
    """
    await websocket.accept()
    job_id = None
    pubsub = None
    forward_task = None
    
    try:
        # Generate unique job ID for this stream
        job_id = str(uuid.uuid4())
        logger.info(f"WebSocket stream connected: {job_id}")
        
        # Send initial message
        await websocket.send_json({
            "type": "connected",
            "job_id": job_id,
            "message": "Ready to receive audio stream"
        })
        
        # Subscribe to transcription results in real-time
        pubsub = await redis_client.subscribe_transcript_results(job_id)
        
        # Create task to forward results from Redis to WebSocket
        async def forward_results():
            """
            WHY: Non-blocking result forwarding
            Continuously listen for transcription results and send to client
            """
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = json.loads(message["data"])
                        await websocket.send_json({
                            "type": "transcript",
                            **data
                        })
            except Exception as e:
                logger.error(f"Error forwarding results: {e}")
        
        forward_task = asyncio.create_task(forward_results())
        
        # Receive audio chunks from client
        audio_format = None
        sample_rate = None
        chunk_index = 0
        
        while True:
            try:
                # Receive with timeout (5 minutes)
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=300.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"WebSocket timeout for {job_id}")
                await websocket.send_json({
                    "type": "error",
                    "error": "Connection timeout - no data received"
                })
                break
            
            message_type = data.get("type")
            
            if message_type == "start":
                # Client indicates streaming start
                audio_format = data.get("format", "wav")
                sample_rate = data.get("sample_rate", 16000)
                
                logger.info(
                    f"Stream starting for {job_id}: "
                    f"format={audio_format}, sample_rate={sample_rate}"
                )
                
                # Publish status to Redis
                await redis_client.publish_stream_status(
                    job_id,
                    "receiving",
                    {"format": audio_format, "sample_rate": sample_rate}
                )
                
                # Update job status
                await redis_client.set_job_status(job_id, "stream_receiving")
                
                await websocket.send_json({
                    "type": "status",
                    "status": "receiving",
                    "message": "Audio reception started"
                })
            
            elif message_type == "audio":
                # Receive audio chunk from client
                chunk_data = data.get("data")
                chunk_idx = data.get("index", chunk_index)
                
                if not chunk_data:
                    logger.warning(f"Empty audio chunk received for {job_id}")
                    continue
                
                logger.debug(
                    f"Received chunk {chunk_idx}: {len(chunk_data)} bytes"
                )
                
                # WHY: Publish to Audio Processor in real-time
                # Enables streaming audio preprocessing
                await redis_client.publish_audio_chunk(
                    job_id,
                    chunk_data,
                    chunk_idx
                )
                
                # Send acknowledgment
                await websocket.send_json({
                    "type": "ack",
                    "chunk_index": chunk_idx,
                    "message": f"Chunk {chunk_idx} received"
                })
                
                chunk_index = chunk_idx + 1
            
            elif message_type == "end":
                # Client indicates end of stream
                logger.info(f"Stream ending for job {job_id}")
                
                # Publish completion status
                await redis_client.publish_stream_status(
                    job_id,
                    "processing_complete",
                    {"total_chunks": chunk_index}
                )
                
                await redis_client.set_job_status(job_id, "stream_complete")
                
                await websocket.send_json({
                    "type": "status",
                    "status": "processing",
                    "message": f"Received {chunk_index} chunks, processing..."
                })
                
                # Wait for transcription to complete (120 second timeout)
                try:
                    await asyncio.wait_for(forward_task, timeout=120.0)
                except asyncio.TimeoutError:
                    logger.error(f"Transcription timeout for job {job_id}")
                    await websocket.send_json({
                        "type": "error",
                        "error": "Transcription processing timed out"
                    })
                
                break
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
    
    except WebSocketDisconnect:
        # WHY: Handle client disconnect gracefully
        logger.warning(f"Client disconnected: {job_id}")
        
        # Clean up subscriptions
        if pubsub:
            await redis_client.unsubscribe_all(pubsub)
        
        # Mark job as abandoned
        if job_id:
            await redis_client.set_job_status(job_id, "stream_abandoned")
            await redis_client.publish_stream_status(job_id, "abandoned")
    
    except Exception as e:
        # WHY: Comprehensive error handling
        logger.error(f"WebSocket error for {job_id}: {str(e)}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "error": f"Server error: {str(e)}"
            })
        except:
            pass
    
    finally:
        # Cleanup subscriptions and tasks
        if pubsub:
            try:
                await redis_client.unsubscribe_all(pubsub)
            except:
                pass
        
        if forward_task:
            forward_task.cancel()
            try:
                await forward_task
            except asyncio.CancelledError:
                pass


@app.get("/ws-test")
async def websocket_test_client():
    """
    HTML test page for WebSocket streaming.
    
    WHY: Simple page to test streaming without building full client
    Useful for debugging and verification.
    """
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket STT Streaming Test</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f5f5f5;
                padding: 20px;
            }
            .container { 
                max-width: 900px; 
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #333; margin-bottom: 10px; }
            .subtitle { color: #666; margin-bottom: 20px; }
            
            .controls {
                display: flex;
                gap: 10px;
                margin: 20px 0;
                flex-wrap: wrap;
            }
            
            button {
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                transition: all 0.3s;
            }
            
            button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            .btn-primary {
                background: #2196F3;
                color: white;
            }
            .btn-primary:hover:not(:disabled) { background: #1976D2; }
            
            .btn-success {
                background: #4CAF50;
                color: white;
            }
            .btn-success:hover:not(:disabled) { background: #388E3C; }
            
            .btn-danger {
                background: #f44336;
                color: white;
            }
            .btn-danger:hover:not(:disabled) { background: #d32f2f; }
            
            .status-box {
                padding: 15px;
                border-radius: 5px;
                margin: 15px 0;
                font-weight: 500;
                display: none;
            }
            
            .status-box.show { display: block; }
            .status-connected { 
                background: #e3f2fd; 
                color: #1565c0;
                border-left: 4px solid #2196F3;
            }
            .status-receiving { 
                background: #fff3e0; 
                color: #e65100;
                border-left: 4px solid #ff9800;
            }
            .status-processing { 
                background: #f3e5f5; 
                color: #6a1b9a;
                border-left: 4px solid #9c27b0;
            }
            .status-completed { 
                background: #e8f5e9; 
                color: #1b5e20;
                border-left: 4px solid #4CAF50;
            }
            .status-error { 
                background: #ffebee; 
                color: #b71c1c;
                border-left: 4px solid #f44336;
            }
            
            .section {
                margin: 30px 0;
            }
            
            .section h2 {
                font-size: 16px;
                color: #333;
                margin-bottom: 10px;
                border-bottom: 2px solid #eee;
                padding-bottom: 10px;
            }
            
            #transcript {
                border: 1px solid #ddd;
                padding: 15px;
                height: 250px;
                overflow-y: auto;
                background: #fafafa;
                border-radius: 5px;
                font-size: 14px;
                line-height: 1.6;
            }
            
            .transcript-segment {
                margin: 10px 0;
                padding: 8px;
                background: white;
                border-radius: 3px;
                border-left: 3px solid #2196F3;
            }
            
            .segment-time {
                color: #666;
                font-size: 12px;
                margin-right: 10px;
            }
            
            .segment-text {
                color: #333;
            }
            
            .segment-confidence {
                color: #999;
                font-size: 12px;
                margin-left: 10px;
            }
            
            #result {
                background: #e8f5e9;
                padding: 15px;
                border-radius: 5px;
                border-left: 4px solid #4CAF50;
                font-size: 15px;
                line-height: 1.6;
                color: #1b5e20;
            }
            
            #log {
                background: #263238;
                color: #aed581;
                padding: 15px;
                border-radius: 5px;
                height: 250px;
                overflow-y: auto;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                line-height: 1.5;
            }
            
            .log-line {
                margin: 2px 0;
            }
            
            .log-info { color: #81c784; }
            .log-error { color: #e57373; }
            .log-warning { color: #ffb74d; }
            
            input[type="file"] {
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 5px;
            }
            
            .grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-top: 20px;
            }
            
            @media (max-width: 768px) {
                .grid { grid-template-columns: 1fr; }
                .controls { flex-direction: column; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎤 WebSocket STT Streaming</h1>
            <p class="subtitle">Real-time streaming speech-to-text transcription</p>
            
            <!-- Status Display -->
            <div id="status" class="status-box"></div>
            
            <!-- Controls -->
            <div class="controls">
                <input type="file" id="audioFile" accept="audio/*" />
                <button class="btn-primary" onclick="connectWebSocket()">Connect WebSocket</button>
                <button class="btn-success" id="startBtn" onclick="startStream()" disabled>Start Stream</button>
                <button class="btn-danger" id="stopBtn" onclick="stopStream()" disabled>Stop Stream</button>
            </div>
            
            <div class="grid">
                <!-- Left Column -->
                <div>
                    <div class="section">
                        <h2>📝 Real-time Transcript</h2>
                        <div id="transcript"></div>
                    </div>
                </div>
                
                <!-- Right Column -->
                <div>
                    <div class="section">
                        <h2>📊 Debug Log</h2>
                        <div id="log"></div>
                    </div>
                </div>
            </div>
            
            <!-- Final Result -->
            <div class="section">
                <h2>✅ Final Result</h2>
                <div id="result" style="display: none;"></div>
                <p id="resultPlaceholder" style="color: #999;">Waiting for transcription...</p>
            </div>
        </div>

        <script>
            let ws = null;
            let isStreaming = false;
            
            function log(message, type = 'info') {
                const logEl = document.getElementById('log');
                const timestamp = new Date().toLocaleTimeString();
                const line = document.createElement('div');
                line.className = `log-line log-${type}`;
                line.textContent = `[${timestamp}] ${message}`;
                logEl.appendChild(line);
                logEl.scrollTop = logEl.scrollHeight;
            }
            
            function setStatus(statusText, cssClass) {
                const statusEl = document.getElementById('status');
                statusEl.textContent = statusText;
                statusEl.className = `status-box show ${cssClass}`;
            }
            
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const url = protocol + '//' + window.location.host + '/v1/stt/stream';
                
                log(`Connecting to ${url}...`, 'info');
                ws = new WebSocket(url);
                
                ws.onopen = () => {
                    log('✓ WebSocket connected', 'info');
                    setStatus('Connected and ready', 'status-connected');
                    document.getElementById('startBtn').disabled = false;
                };
                
                ws.onmessage = (event) => {
                    const msg = JSON.parse(event.data);
                    
                    if (msg.type === 'connected') {
                        log(`Job ID: ${msg.job_id}`, 'info');
                    } else if (msg.type === 'status') {
                        log(`Status: ${msg.status}`, 'info');
                        const cssClass = `status-${msg.status}`;
                        setStatus(msg.status, cssClass);
                    } else if (msg.type === 'transcript') {
                        log(`Segment: ${msg.text}`, 'info');
                        const transcriptEl = document.getElementById('transcript');
                        const segment = document.createElement('div');
                        segment.className = 'transcript-segment';
                        segment.innerHTML = `
                            <span class="segment-time">[${msg.start.toFixed(2)}s-${msg.end.toFixed(2)}s]</span>
                            <span class="segment-text">${msg.text}</span>
                            <span class="segment-confidence">(${(msg.confidence * 100).toFixed(0)}%)</span>
                        `;
                        transcriptEl.appendChild(segment);
                        transcriptEl.scrollTop = transcriptEl.scrollHeight;
                    } else if (msg.type === 'result') {
                        log('✓ Transcription completed', 'info');
                        document.getElementById('resultPlaceholder').style.display = 'none';
                        const resultEl = document.getElementById('result');
                        resultEl.textContent = msg.text;
                        resultEl.style.display = 'block';
                        setStatus('Completed', 'status-completed');
                    } else if (msg.type === 'ack') {
                        log(`Ack: ${msg.chunk_index}`, 'info');
                    } else if (msg.type === 'error') {
                        log(`Error: ${msg.error}`, 'error');
                        setStatus(`Error: ${msg.error}`, 'status-error');
                    }
                };
                
                ws.onerror = (error) => {
                    log('✗ WebSocket error: ' + error, 'error');
                    setStatus('Error', 'status-error');
                };
                
                ws.onclose = () => {
                    log('WebSocket closed', 'warning');
                    setStatus('Disconnected', 'status-error');
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('stopBtn').disabled = true;
                };
            }
            
            async function startStream() {
                const fileInput = document.getElementById('audioFile');
                const audioFile = fileInput.files[0];
                
                if (!audioFile) {
                    alert('Please select an audio file');
                    return;
                }
                
                if (!ws || ws.readyState !== WebSocket.OPEN) {
                    alert('WebSocket not connected');
                    return;
                }
                
                document.getElementById('transcript').innerHTML = '';
                document.getElementById('result').style.display = 'none';
                document.getElementById('resultPlaceholder').style.display = 'block';
                
                isStreaming = true;
                document.getElementById('startBtn').disabled = true;
                document.getElementById('stopBtn').disabled = false;
                
                ws.send(JSON.stringify({
                    type: 'start',
                    format: 'wav',
                    sample_rate: 16000
                }));
                
                log(`Starting stream: ${audioFile.name} (${(audioFile.size / 1024).toFixed(2)} KB)`, 'info');
                
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const arrayBuffer = e.target.result;
                    const base64 = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
                    
                    const chunkSize = 20 * 1024; // 20KB chunks
                    for (let i = 0; i < base64.length && isStreaming; i += chunkSize) {
                        const chunk = base64.substring(i, i + chunkSize);
                        ws.send(JSON.stringify({
                            type: 'audio',
                            data: chunk,
                            index: Math.floor(i / chunkSize)
                        }));
                        
                        await new Promise(resolve => setTimeout(resolve, 50));
                    }
                    
                    if (isStreaming) {
                        ws.send(JSON.stringify({ type: 'end' }));
                        log('Stream ended', 'info');
                        isStreaming = false;
                        document.getElementById('stopBtn').disabled = true;
                    }
                };
                
                reader.readAsArrayBuffer(audioFile);
            }
            
            function stopStream() {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'end' }));
                    isStreaming = false;
                    document.getElementById('stopBtn').disabled = true;
                    log('Stream stopped', 'warning');
                }
            }
        </script>
    </body>
    </html>
    """)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT") != "production",
    )
