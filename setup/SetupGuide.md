# Setup Guide

This directory contains setup scripts for the Speech-to-Text API on different platforms.

## Quick Start

### Windows
```bash
cd setup
setup.bat
```

### macOS / Linux
```bash
cd setup
chmod +x setup.sh
./setup.sh
```

### Cross-Platform (Python)
```bash
python setup/setup.py
```

## What Each Script Does

1. **Checks** if Python 3.10+ is installed
2. **Creates** a Python virtual environment (`venv` folder)
3. **Installs** required dependencies (`requests`)
4. **Creates** `.env` file from `.env.example` (if not exists)
5. **Provides** instructions for next steps

## Platform-Specific Details

### Windows (`setup.bat`)

**Requirements:**
- Python 3.10+ with "Add to PATH" option checked
- Administrator privileges (optional, for some system packages)

**What it does:**
- Uses `cmd.exe` and batch commands
- Creates `venv\Scripts\activate.bat`
- Works with Windows PowerShell and Command Prompt

**Activate virtual environment:**
```cmd
venv\Scripts\activate
```

**Deactivate:**
```cmd
deactivate
```

### macOS / Linux (`setup.sh`)

**Requirements:**
- Python 3.10+
- Bash shell

**Installation (if Python missing):**

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install python3 python3-venv python3-pip
```

**macOS (with Homebrew):**
```bash
brew install python@3.11
```

**What it does:**
- Uses bash shell commands
- Creates `venv/bin/activate`
- Uses standard Unix directory structure

**Activate virtual environment:**
```bash
source venv/bin/activate
```

**Deactivate:**
```bash
deactivate
```

### Cross-Platform (`setup.py`)

**Requirements:**
- Python 3.10+
- Works on all platforms

**What it does:**
- Detects your OS automatically
- Works with Windows, macOS, and Linux
- Provides colored output on supported terminals

**Run:**
```bash
python setup/setup.py
```

## After Setup

### 1. Activate Virtual Environment

**Windows:**
```cmd
venv\Scripts\activate
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

### 2. Verify Installation

```bash
python --version
pip list
```

### 3. Run Tests

```bash
# With local audio file
python test_endpoints_simple.py audio/sample_audio.mp3

# With cloud-based audio
python test_endpoints_simple.py "https://example.com/audio.mp3"
```

### 4. Start Services

```bash
# Requires Docker and Docker Compose
docker-compose up -d
```

## Configuration

The setup creates a `.env` file with default settings. You can modify it:

```bash
# Edit .env file with your preferred editor
nano .env           # macOS/Linux
notepad .env        # Windows
```

**Key configuration options:**

- `REDIS_URL`: Redis connection string
- `PORT`: API server port (default: 8000)
- `LOG_LEVEL`: Logging verbosity
- `WHISPER_MODEL`: Whisper model size (tiny/base/small/medium/large)
- `MAX_FILE_SIZE`: Maximum upload size in MB

See `.env.example` for all options and descriptions.

## Troubleshooting

### Python not found

**Windows:**
- Reinstall Python and check "Add Python to PATH"
- Use full path: `C:\Python311\python.exe -m venv venv`

**macOS/Linux:**
- Check if Python 3 is installed: `python3 --version`
- May need to use `python3` instead of `python`

### Virtual environment fails to create

**Issue:** Permission denied or disk space

**Solution:**
```bash
# Delete existing venv and try again
rm -rf venv              # macOS/Linux
rmdir /s venv           # Windows
python -m venv venv
```

### pip installation fails

**Issue:** Network or package compatibility

**Solution:**
```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Install with specific index
pip install -i https://pypi.org/simple/ requests
```

### .env file not created

**Solution:** Manually create it:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**macOS/Linux:**
```bash
cp .env.example .env
```

## Virtual Environment Management

### View installed packages
```bash
pip list
```

### Save current environment
```bash
pip freeze > requirements.txt
```

### Update a package
```bash
pip install --upgrade <package_name>
```

### Remove virtual environment
```bash
# macOS/Linux
rm -rf venv

# Windows
rmdir /s venv
```

## Directory Structure

```
setup/
├── setup.bat        # Windows batch script
├── setup.sh         # macOS/Linux bash script
├── setup.py         # Cross-platform Python script
└── README.md        # This file

../
├── .env             # Environment configuration (created by setup)
├── .env.example     # Example environment file
├── venv/            # Virtual environment (created by setup)
│   ├── bin/         # Executables (macOS/Linux)
│   ├── Scripts/     # Executables (Windows)
│   └── lib/         # Python packages
└── ...other files...
```

## Additional Resources

- **Python:** https://www.python.org/
- **Virtual Environments:** https://docs.python.org/3/tutorial/venv.html
- **Docker:** https://www.docker.com/
- **Project README:** `../README.md`

## Support

If you encounter issues:

1. Check the error message in the console
2. Review the troubleshooting section above
3. Ensure Python 3.10+ is installed
4. Try the cross-platform Python setup: `python setup/setup.py`

---

Happy coding! 🚀
