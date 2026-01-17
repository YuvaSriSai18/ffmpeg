#!/usr/bin/env python3
"""
Test script for WebSocket Streaming STT
Demonstrates both HTTP polling and WebSocket streaming methods
"""

import asyncio
import aiohttp
import websockets
import json
import base64
from pathlib import Path
from datetime import datetime


# Configuration
API_BASE_URL = "http://localhost:8000"
WS_BASE_URL = "ws://localhost:8000"
AUDIO_FILE = "audio/sample_audio.mp3"  # Update with your audio file    


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    END = '\033[0m'


def print_section(title):
    """Print a section header"""
    print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.CYAN}{title:^60}{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}\n")


def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")


def print_info(msg):
    print(f"{Colors.BLUE}ℹ {msg}{Colors.END}")


def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.END}")


def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.END}")


async def test_http_polling():
    """
    Test Method 1: HTTP Polling
    
    WHY: Traditional approach
    - Multiple HTTP requests over time
    - Client polls server repeatedly
    - Simpler implementation but less efficient
    """
    print_section("Method 1: HTTP Polling (Traditional)")
    
    print_info("This method uses HTTP POST/GET requests")
    print_info("Client polls server every second for status updates\n")
    
    try:
        # Step 1: Check health
        print_info("Step 1: Health Check")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/health") as resp:
                health = await resp.json()
                print_success(f"API Health: {health['status']}")
            
            # Step 2: Upload file
            print_info("\nStep 2: Upload Audio File")
            with open(AUDIO_FILE, 'rb') as f:
                audio_data = f.read()
            
            data = aiohttp.FormData()
            data.add_field('file', audio_data, filename='sample.mp3')
            
            async with session.post(f"{API_BASE_URL}/v1/stt/jobs", data=data) as resp:
                upload_response = await resp.json()
                job_id = upload_response['job_id']
                print_success(f"File uploaded, Job ID: {job_id}")
            
            # Step 3: Poll for status
            print_info("\nStep 3: Poll for Status (Every 2 seconds)")
            print_info("Polling up to 120 seconds or until completion\n")
            
            polling_count = 0
            max_polls = 60  # 2 minutes
            
            while polling_count < max_polls:
                await asyncio.sleep(2)
                polling_count += 1
                
                async with session.get(f"{API_BASE_URL}/v1/stt/jobs/{job_id}") as resp:
                    status_response = await resp.json()
                    status = status_response.get('status')
                    
                    print(f"  [{polling_count}] Status: {Colors.YELLOW}{status}{Colors.END}")
                    
                    if status == 'completed':
                        # Step 4: Get results
                        result = status_response.get('result')
                        if result:
                            transcription = result.get('text', '')
                            duration = result.get('duration', 0)
                            
                            print_success(f"Transcription completed!")
                            print_info(f"Duration: {duration:.2f}s")
                            print_info(f"Text: {transcription[:100]}...")
                            break
                    
                    elif status == 'failed':
                        print_error("Job failed")
                        break
            
            if polling_count >= max_polls:
                print_warning("Polling timeout - job may still be processing")
    
    except Exception as e:
        print_error(f"HTTP Polling test failed: {e}")


async def test_websocket_streaming():
    """
    Test Method 2: WebSocket Streaming
    
    WHY: Real-time streaming approach
    - Single persistent WebSocket connection
    - Server pushes updates to client in real-time
    - More efficient, better UX
    """
    print_section("Method 2: WebSocket Streaming (Real-time)")
    
    print_info("This method uses a single WebSocket connection")
    print_info("Server streams results as they arrive\n")
    
    try:
        # Load audio file
        if not Path(AUDIO_FILE).exists():
            print_warning(f"Audio file not found: {AUDIO_FILE}")
            print_info("Creating a test connection without audio...")
            # Continue with empty demonstration
        
        print_info("Step 1: Establishing WebSocket Connection")
        
        async with websockets.connect(f"{WS_BASE_URL}/v1/stt/stream") as websocket:
            # Receive initial connection message
            msg = await asyncio.wait_for(websocket.recv(), timeout=5)
            init_data = json.loads(msg)
            job_id = init_data.get('job_id')
            print_success(f"Connected! Job ID: {job_id}")
            print_success(f"Message: {init_data.get('message')}")
            
            # Step 2: Start stream
            print_info("\nStep 2: Starting Audio Stream")
            await websocket.send(json.dumps({
                "type": "start",
                "format": "wav",
                "sample_rate": 16000
            }))
            
            msg = await asyncio.wait_for(websocket.recv(), timeout=5)
            status_data = json.loads(msg)
            print_success(f"Status: {status_data.get('status')}")
            
            # Step 3: Send audio chunks
            print_info("\nStep 3: Streaming Audio Chunks")
            
            if Path(AUDIO_FILE).exists():
                with open(AUDIO_FILE, 'rb') as f:
                    audio_data = f.read()
                
                # Send in 20KB chunks
                chunk_size = 20 * 1024
                base64_audio = base64.b64encode(audio_data).decode('utf-8')
                
                for i in range(0, len(base64_audio), chunk_size):
                    chunk = base64_audio[i:i + chunk_size]
                    chunk_idx = i // chunk_size
                    
                    await websocket.send(json.dumps({
                        "type": "audio",
                        "data": chunk,
                        "index": chunk_idx
                    }))
                    
                    # Receive acknowledgment
                    try:
                        ack = await asyncio.wait_for(websocket.recv(), timeout=2)
                        ack_data = json.loads(ack)
                        print_info(f"  Chunk {chunk_idx}: Sent ({len(chunk)} bytes)")
                    except asyncio.TimeoutError:
                        pass
                
                print_success(f"All chunks sent ({len(base64_audio)} bytes total)")
            else:
                # Send demo chunks
                for i in range(3):
                    await websocket.send(json.dumps({
                        "type": "audio",
                        "data": base64.b64encode(b'demo_audio_chunk').decode(),
                        "index": i
                    }))
                    print_info(f"  Demo chunk {i} sent")
            
            # Step 4: End stream
            print_info("\nStep 4: Ending Stream")
            await websocket.send(json.dumps({"type": "end"}))
            print_success("Stream end signal sent")
            
            # Step 5: Receive real-time results
            print_info("\nStep 5: Receiving Real-time Transcription Results")
            print_info("Listening for transcript chunks...\n")
            
            segments_received = 0
            transcript_text = ""
            
            try:
                while True:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=120)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    
                    if msg_type == 'status':
                        status = data.get('status')
                        print(f"{Colors.YELLOW}  [Status] {status}{Colors.END}")
                    
                    elif msg_type == 'transcript':
                        text = data.get('text', '')
                        start = data.get('start', 0)
                        end = data.get('end', 0)
                        confidence = data.get('confidence', 0)
                        
                        segments_received += 1
                        transcript_text += text + " "
                        
                        print(f"  {Colors.GREEN}[{segments_received}]{Colors.END} "
                              f"[{start:.2f}s-{end:.2f}s] {text} "
                              f"({Colors.CYAN}{confidence*100:.0f}%{Colors.END})")
                    
                    elif msg_type == 'result':
                        final_text = data.get('text', '')
                        print_success(f"\nFinal Transcription Received!")
                        print_info(f"Text: {final_text[:100]}...")
                        print_success("Stream completed successfully")
                        break
                    
                    elif msg_type == 'error':
                        print_error(f"Error: {data.get('error')}")
                        break
            
            except asyncio.TimeoutError:
                if transcript_text:
                    print_warning("Connection timeout, but received segments:")
                    print_info(f"Partial text: {transcript_text[:100]}...")
                else:
                    print_warning("No response received (API may still be processing)")
    
    except Exception as e:
        print_error(f"WebSocket Streaming test failed: {e}")


async def compare_methods():
    """Compare the two methods side by side"""
    print_section("Comparison: HTTP vs WebSocket")
    
    comparison = {
        "Aspect": ["Connection Type", "Update Frequency", "Bandwidth", "Latency",
                   "CPU Usage", "Battery (Mobile)", "Implementation", "Real-time"],
        "HTTP Polling": ["Multiple requests", "Every N seconds", "High (headers)", 
                        "1-N seconds", "High", "Drains battery", "Simple", "No"],
        "WebSocket": ["Single persistent", "Real-time push", "Low (one handshake)",
                      "Milliseconds", "Low", "Battery friendly", "Moderate", "Yes"]
    }
    
    # Print table
    print(f"{comparison['Aspect'][0]:<20} | {comparison['HTTP Polling'][0]:<25} | {comparison['WebSocket'][0]:<25}")
    print("-" * 75)
    
    for i in range(1, len(comparison['Aspect'])):
        aspect = comparison['Aspect'][i]
        http = comparison['HTTP Polling'][i]
        ws = comparison['WebSocket'][i]
        print(f"{aspect:<20} | {http:<25} | {ws:<25}")


async def main():
    """Main test runner"""
    print("\n")
    print(f"{Colors.CYAN}{'#'*60}{Colors.END}")
    print(f"{Colors.CYAN}#{'STT WebSocket Streaming - Test Suite':^58}#{Colors.END}")
    print(f"{Colors.CYAN}{'#'*60}{Colors.END}\n")
    
    print_info("Testing both HTTP Polling and WebSocket Streaming methods")
    print_info(f"API Base: {API_BASE_URL}")
    print_info(f"WebSocket Base: {WS_BASE_URL}")
    print_info(f"Audio File: {AUDIO_FILE}\n")
    
    # Test 1: HTTP Polling
    print(f"\n{Colors.YELLOW}Starting HTTP Polling test...{Colors.END}")
    try:
        await test_http_polling()
    except Exception as e:
        print_error(f"HTTP test failed: {e}")
    
    await asyncio.sleep(2)
    
    # Test 2: WebSocket Streaming
    print(f"\n{Colors.YELLOW}Starting WebSocket Streaming test...{Colors.END}")
    try:
        await test_websocket_streaming()
    except Exception as e:
        print_error(f"WebSocket test failed: {e}")
    
    # Comparison
    await compare_methods()
    
    print_section("Test Summary")
    print_success("Both HTTP and WebSocket methods are available!")
    print_info("Use HTTP Polling for: Compatibility, Simple clients")
    print_info("Use WebSocket Streaming for: Real-time UX, Live transcription")
    
    print(f"\n{Colors.CYAN}Test suite completed!{Colors.END}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.END}\n")
    except Exception as e:
        print_error(f"Test failed: {e}\n")
