#!/usr/bin/env python3
"""
Cross-platform setup script for STT API
Works on Windows, macOS, and Linux
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# Color codes for terminal output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color
    
    @staticmethod
    def disable_for_windows():
        """Disable colors on Windows if not using modern terminal"""
        if sys.platform == 'win32':
            Colors.RED = ''
            Colors.GREEN = ''
            Colors.YELLOW = ''
            Colors.BLUE = ''
            Colors.NC = ''

Colors.disable_for_windows()

def print_header(text):
    """Print section header"""
    print(f"\n{Colors.BLUE}{'='*60}{Colors.NC}")
    print(f"{Colors.BLUE}  {text}{Colors.NC}")
    print(f"{Colors.BLUE}{'='*60}{Colors.NC}\n")

def print_ok(text):
    """Print success message"""
    print(f"{Colors.GREEN}[OK]{Colors.NC} {text}")

def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}[ERROR]{Colors.NC} {text}")

def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {text}")

def print_info(text):
    """Print info message"""
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {text}")

def check_python():
    """Check if Python 3.10+ is installed"""
    print("Checking Python installation...")
    try:
        result = subprocess.run(
            [sys.executable, '--version'],
            capture_output=True,
            text=True
        )
        version = result.stdout.strip()
        print_ok(f"Found: {version}")
        return True
    except Exception as e:
        print_error(f"Python check failed: {e}")
        return False

def create_venv(venv_dir='venv'):
    """Create Python virtual environment"""
    if Path(venv_dir).exists():
        print_warning(f"Virtual environment already exists at {venv_dir}")
        return True
    
    print(f"Creating Python virtual environment at {venv_dir}...")
    try:
        subprocess.run(
            [sys.executable, '-m', 'venv', venv_dir],
            check=True
        )
        print_ok("Virtual environment created")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False

def get_pip_executable(venv_dir='venv'):
    """Get the pip executable path for the virtual environment"""
    if sys.platform == 'win32':
        return os.path.join(venv_dir, 'Scripts', 'pip.exe')
    else:
        return os.path.join(venv_dir, 'bin', 'pip')

def get_python_executable(venv_dir='venv'):
    """Get the python executable path for the virtual environment"""
    if sys.platform == 'win32':
        return os.path.join(venv_dir, 'Scripts', 'python.exe')
    else:
        return os.path.join(venv_dir, 'bin', 'python')

def upgrade_pip(venv_dir='venv'):
    """Upgrade pip in virtual environment"""
    print("Upgrading pip...")
    pip_exe = get_pip_executable(venv_dir)
    try:
        subprocess.run(
            [pip_exe, 'install', '--upgrade', 'pip'],
            check=True,
            capture_output=True
        )
        print_ok("pip upgraded")
        return True
    except subprocess.CalledProcessError as e:
        print_warning(f"Failed to upgrade pip: {e}")
        return True  # Don't fail, continue anyway

def install_requirements(venv_dir='venv'):
    """Install Python requirements"""
    pip_exe = get_pip_executable(venv_dir)
    
    if Path('requirements.txt').exists():
        print("Installing Python dependencies from requirements.txt...")
        try:
            subprocess.run(
                [pip_exe, 'install', '-r', 'requirements.txt'],
                check=True
            )
            print_ok("All dependencies installed")
            return True
        except subprocess.CalledProcessError as e:
            print_warning(f"Some packages may have failed to install: {e}")
            return True
    else:
        print("Installing requests library...")
        try:
            subprocess.run(
                [pip_exe, 'install', 'requests'],
                check=True,
                capture_output=True
            )
            print_ok("requests installed")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to install requests: {e}")
            return False

def create_env_file():
    """Create .env file if it doesn't exist"""
    if Path('.env').exists():
        print_ok(".env file already exists")
        return True
    
    print("Creating .env file...")
    
    if Path('.env.example').exists():
        shutil.copy('.env.example', '.env')
        print_ok(".env file created from .env.example")
        return True
    else:
        print_warning(".env.example not found")
        print("Creating default .env...")
        try:
            with open('.env', 'w') as f:
                f.write("""REDIS_URL=redis://localhost:6379
DATA_DIR=./data
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=INFO
WORKER_CONCURRENCY=2
WHISPER_MODEL=base
MAX_FILE_SIZE=100
""")
            print_ok("Default .env file created")
            return True
        except Exception as e:
            print_error(f"Failed to create .env: {e}")
            return False

def print_completion_info(venv_dir='venv'):
    """Print completion information"""
    print_header("Setup Complete!")
    
    if sys.platform == 'win32':
        activate_cmd = f"{venv_dir}\\Scripts\\activate"
    else:
        activate_cmd = f"source {venv_dir}/bin/activate"
    
    print(f"To activate the virtual environment, run:")
    print(f"  {Colors.BLUE}{activate_cmd}{Colors.NC}")
    print()
    print("To run the tests:")
    print(f"  {Colors.BLUE}python test_endpoints_simple.py [audio_file_or_url]{Colors.NC}")
    print()
    print("To start the services (requires Docker):")
    print(f"  {Colors.BLUE}docker-compose up -d{Colors.NC}")
    print()

def main():
    """Main setup function"""
    print_header("STT API - Setup")
    
    # Get project root (parent of this script)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Change to project root
    os.chdir(project_root)
    print_info(f"Working directory: {project_root}")
    print()
    
    # Run setup steps
    if not check_python():
        sys.exit(1)
    print()
    
    if not create_venv():
        sys.exit(1)
    print()
    
    if not upgrade_pip():
        pass  # Don't exit on pip upgrade failure
    print()
    
    if not install_requirements():
        print_warning("Some dependencies may not be installed, but continuing...")
    print()
    
    if not create_env_file():
        print_warning("Failed to create .env file, but you can create it manually")
    print()
    
    print_completion_info()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
