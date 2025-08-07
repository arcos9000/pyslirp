#!/bin/bash
# PyLiRP Installation Launcher for Linux
# Launches the virtual environment-aware installation script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo "PyLiRP Linux Installation Launcher"
echo "=================================="
echo

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    print_status "Running as root - will perform system installation"
    print_status "Using virtual environment-aware installer..."
    echo
    
    # Launch the virtual environment installer
    exec bash "$SCRIPT_DIR/install_linux_venv.sh" "$@"
else
    print_error "This installer requires root privileges for system installation"
    print_status "Please run: sudo $0"
    echo
    print_status "Alternative: For user-only installation, you can:"
    print_status "1. Create a virtual environment manually:"
    print_status "   python3 -m venv ~/.pyslirp-venv"
    print_status "   source ~/.pyslirp-venv/bin/activate"
    print_status "   pip install -r requirements.txt"
    print_status "2. Run PyLiRP directly:"
    print_status "   ~/.pyslirp-venv/bin/python main.py /dev/ttyUSB0"
    echo
    exit 1
fi