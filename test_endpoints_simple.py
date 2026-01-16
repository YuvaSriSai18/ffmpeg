#!/usr/bin/env python3
"""
Simple Python test script for all STT API endpoints.
Tests the complete workflow with the sample audio file.
Supports both local and cloud-based audio sources.
"""
import requests
import time
import sys
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

API_BASE = "http://localhost:8000"
# Default to local file, but can be overridden by environment variable or command line
# AUDIO_FILE = os.getenv("AUDIO_FILE", "audio/sample_audio.mp3")
AUDIO_FILE = "https://firebasestorage.googleapis.com/v0/b/cloud0924.appspot.com/o/sample-3.mp3?alt=media&token=75210a4c-7c33-4024-bfeb-adcaac659dbf"

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)

def print_test(number, total, name):
    print(f"\n[Test {number}/{total}] {name}")
    print("-" * 60)

def is_url(path: str) -> bool:
    """Check if path is a URL."""
    try:
        result = urlparse(path)
        return result.scheme in ('http', 'https', 's3', 'gs', 'az')
    except Exception:
        return False

def download_file(url: str, timeout: int = 30) -> tuple[Path, str]:
    """
    Download file from URL to temporary location.
    
    Returns:
        Tuple of (Path to temp file, original filename)
    """
    try:
        print(f"  Downloading from: {url}")
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()
        
        # Get filename from URL or use default
        content_disposition = response.headers.get('content-disposition', '')
        if 'filename=' in content_disposition:
            filename = content_disposition.split('filename=')[1].strip('"\'')
        else:
            filename = urlparse(url).path.split('/')[-1] or 'audio.mp3'
        
        # Create temp file with proper extension
        if not filename or '.' not in filename:
            filename = 'audio.mp3'
        
        # Download to temp directory
        temp_dir = tempfile.gettempdir()
        temp_path = Path(temp_dir) / f"stt_test_{filename}"
        
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        print(f"  ✓ Downloaded successfully to: {temp_path}")
        return temp_path, filename
        
    except Exception as e:
        print(f"  ❌ Download failed: {e}")
        raise

def get_audio_file(location: str) -> tuple[Path, str]:
    """
    Get audio file from local or cloud location.
    
    Args:
        location: Local file path or cloud URL
        
    Returns:
        Tuple of (Path to audio file, original filename)
    """
    if is_url(location):
        return download_file(location)
    else:
        # Local file
        audio_path = Path(location)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {location}")
        return audio_path, audio_path.name

def main():
    print_header("STT API Endpoint Testing")
    print(f"Testing with: {AUDIO_FILE}\n")
    
    # Get audio file (local or cloud)
    try:
        if is_url(AUDIO_FILE):
            print("Detected cloud-based audio source")
            audio_path, filename = get_audio_file(AUDIO_FILE)
        else:
            print("Detected local audio source")
            audio_path, filename = get_audio_file(AUDIO_FILE)
        
        print(f"✓ Audio file ready: {filename}")
        print(f"  Location: {audio_path}")
        print(f"  File size: {audio_path.stat().st_size} bytes")
    except Exception as e:
        print(f"❌ ERROR: Failed to get audio file: {e}")
        return 1
    
    # Test 1: Health Check
    print_test(1, 4, "Health Check Endpoint")
    try:
        response = requests.get(f"{API_BASE}/health")
        response.raise_for_status()
        data = response.json()
        print("✓ Health check passed")
        print(f"  Status: {data.get('status')}")
        print(f"  Service: {data.get('service')}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        print("   Make sure services are running: docker-compose up -d")
        return 1
    
    # Test 2: Root Endpoint
    print_test(2, 4, "Root Endpoint (API Info)")
    try:
        response = requests.get(f"{API_BASE}/")
        response.raise_for_status()
        data = response.json()
        print("✓ Root endpoint passed")
        print(f"  Service: {data.get('service')}")
        print(f"  Version: {data.get('version')}")
        print(f"  Docs: {data.get('docs')}")
    except Exception as e:
        print(f"❌ Root endpoint failed: {e}")
        return 1
    
    # Test 3: Upload Audio File
    print_test(3, 4, "Upload Audio File (Create Job)")
    try:
        with open(audio_path, 'rb') as f:
            files = {'file': (filename, f, 'audio/mpeg')}
            response = requests.post(f"{API_BASE}/v1/stt/jobs", files=files)
            response.raise_for_status()
            data = response.json()
        
        print("✓ Upload successful")
        job_id = data['job_id']
        status_url = data['status_url']
        print(f"  Job ID: {job_id}")
        print(f"  Status URL: {status_url}")
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return 1
    finally:
        # Clean up temp file if it was downloaded
        if is_url(AUDIO_FILE) and audio_path.exists():
            try:
                audio_path.unlink()
                print("  (Cleaned up temporary file)")
            except Exception:
                pass
    
    # Test 4: Check Job Status
    print_test(4, 4, "Job Status & Transcription")
    max_attempts = 60
    attempt = 0
    completed = False
    
    print(f"Waiting for job to complete (max {max_attempts} seconds)...")
    
    while attempt < max_attempts and not completed:
        attempt += 1
        time.sleep(1)
        
        try:
            response = requests.get(f"{API_BASE}/v1/stt/jobs/{job_id}")
            response.raise_for_status()
            data = response.json()
            status = data['status']
            
            print(f"  [{attempt}/{max_attempts}] Status: {status}")
            
            if status == "completed":
                completed = True
                print("✓ Job completed successfully!")
                
                if 'result' in data and data['result']:
                    result = data['result']
                    print("\n" + "="*60)
                    print("  TRANSCRIPTION RESULT")
                    print("="*60)
                    print(f"Text: {result.get('text', 'N/A')}")
                    print(f"Language: {result.get('language', 'N/A')}")
                    print(f"Duration: {result.get('duration', 0):.2f} seconds")
                    if 'segments' in result:
                        print(f"Segments: {len(result['segments'])}")
                    print("="*60)
                else:
                    print("⚠ Job completed but no result found")
                    
            elif status in ["failed", "error"]:
                print(f"❌ Job failed with status: {status}")
                print(f"Response: {data}")
                return 1
                
        except Exception as e:
            print(f"❌ Status check failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"   Response: {e.response.text}")
            return 1
    
    if not completed:
        print(f"\n❌ Job did not complete within {max_attempts} seconds")
        print(f"Last status: {status}")
        return 1
    
    print_header("All Tests Completed Successfully ✓")
    print("Summary:")
    print("  ✓ Health check")
    print("  ✓ Root endpoint")
    print("  ✓ File upload")
    print("  ✓ Job status & transcription")
    print()
    
    return 0

if __name__ == "__main__":
    import sys
    
    # Allow audio file location to be passed as command line argument
    if len(sys.argv) > 1:
        AUDIO_FILE = sys.argv[1]
    
    sys.exit(main())
