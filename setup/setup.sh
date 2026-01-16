#!/bin/bash

################################################################################
# Speech-to-Text API - macOS/Linux Setup Script
################################################################################
# This script sets up the development environment on macOS and Linux
# It creates a virtual environment and installs dependencies
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "============================================================"
echo "   STT API - macOS/Linux Setup"
echo "============================================================"
echo ""

# Check if Python 3 is installed
echo "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] Python 3 is not installed!${NC}"
    echo "Please install Python 3.10+ using:"
    echo "  macOS:  brew install python3"
    echo "  Ubuntu: sudo apt-get install python3 python3-venv python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}[OK] Found: $PYTHON_VERSION${NC}"
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo -e "${YELLOW}[INFO] Virtual environment already exists${NC}"
    echo "Activating existing environment..."
else
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR] Failed to create virtual environment${NC}"
        exit 1
    fi
    echo -e "${GREEN}[OK] Virtual environment created${NC}"
fi

echo ""
echo "Activating virtual environment..."
source venv/bin/activate
echo -e "${GREEN}[OK] Virtual environment activated${NC}"
echo ""

# Upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip > /dev/null 2>&1
echo -e "${GREEN}[OK] pip upgraded${NC}"
echo ""

# Install requirements
if [ -f "requirements.txt" ]; then
    echo "Installing Python dependencies from requirements.txt..."
    pip install -r requirements.txt
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[OK] All dependencies installed${NC}"
    else
        echo -e "${YELLOW}[WARNING] Some packages may have failed to install${NC}"
    fi
else
    echo "Installing requests library..."
    pip install requests
    echo -e "${GREEN}[OK] requests installed${NC}"
fi
echo ""

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${GREEN}[OK] .env file created from .env.example${NC}"
    else
        echo -e "${YELLOW}[WARNING] .env.example not found${NC}"
        echo "Creating default .env..."
        cat > .env << EOF
REDIS_URL=redis://localhost:6379
DATA_DIR=./data
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=INFO
WORKER_CONCURRENCY=2
WHISPER_MODEL=base
MAX_FILE_SIZE=100
EOF
        echo -e "${GREEN}[OK] Default .env file created${NC}"
    fi
else
    echo -e "${GREEN}[OK] .env file already exists${NC}"
fi
echo ""

# Final instructions
echo "============================================================"
echo "   Setup Complete!"
echo "============================================================"
echo ""
echo "To use the virtual environment, run:"
echo "   source venv/bin/activate"
echo ""
echo "To run the tests:"
echo "   python test_endpoints_simple.py [audio_file_or_url]"
echo ""
echo "To start the services (requires Docker):"
echo "   docker-compose up -d"
echo ""
echo "============================================================"
echo ""
