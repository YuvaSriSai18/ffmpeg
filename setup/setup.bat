@echo off
REM ============================================================
REM Speech-to-Text API - Windows Setup Script
REM ============================================================
REM This script sets up the development environment on Windows
REM It creates a virtual environment and installs dependencies
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   STT API - Windows Setup
echo ============================================================
echo.

REM Colors and formatting
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "RESET=[0m"

REM Check if Python is installed
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo !RED![ERROR] Python is not installed or not in PATH!RESET!
    echo Please install Python 3.10+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo !GREEN![OK] Found: %PYTHON_VERSION%!RESET!
echo.

REM Check if virtual environment exists
if exist "venv" (
    echo !YELLOW![INFO] Virtual environment already exists!RESET!
    echo Activating existing environment...
) else (
    echo Creating Python virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo !RED![ERROR] Failed to create virtual environment!RESET!
        exit /b 1
    )
    echo !GREEN![OK] Virtual environment created!RESET!
)

echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo !RED![ERROR] Failed to activate virtual environment!RESET!
    exit /b 1
)
echo !GREEN![OK] Virtual environment activated!RESET!
echo.

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1
echo !GREEN![OK] pip upgraded!RESET!
echo.

REM Install requirements
if exist "requirements.txt" (
    echo Installing Python dependencies from requirements.txt...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo !RED![WARNING] Some packages may have failed to install!RESET!
    ) else (
        echo !GREEN![OK] All dependencies installed!RESET!
    )
) else (
    echo Installing requests library...
    pip install requests
    echo !GREEN![OK] requests installed!RESET!
)
echo.

REM Create .env file if it doesn't exist
if not exist ".env" (
    echo Creating .env file...
    if exist ".env.example" (
        copy .env.example .env >nul
        echo !GREEN![OK] .env file created from .env.example!RESET!
    ) else (
        echo !YELLOW![WARNING] .env.example not found!RESET!
        echo Creating default .env...
        (
            echo REDIS_URL=redis://localhost:6379
            echo DATA_DIR=./data
            echo PORT=8000
            echo ENVIRONMENT=development
            echo LOG_LEVEL=INFO
            echo WORKER_CONCURRENCY=2
            echo WHISPER_MODEL=base
            echo MAX_FILE_SIZE=100
        ) > .env
        echo !GREEN![OK] Default .env file created!RESET!
    )
) else (
    echo !GREEN![OK] .env file already exists!RESET!
)
echo.

REM Final instructions
echo ============================================================
echo   Setup Complete!
echo ============================================================
echo.
echo To use the virtual environment, run:
echo   venv\Scripts\activate
echo.
echo To run the tests:
echo   python test_endpoints_simple.py [audio_file_or_url]
echo.
echo To start the services (requires Docker):
echo   docker-compose up -d
echo.
echo ============================================================
echo.

endlocal
