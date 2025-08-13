#!/bin/bash
# PiKVM-specific installation script for PyLiRP

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== PyLiRP Installation for PiKVM ===${NC}"

# Check if running on PiKVM
if [ ! -f /etc/kvmd/main.yaml ] && [ ! -d /usr/share/kvmd ]; then
    echo -e "${YELLOW}Warning: This doesn't appear to be a PiKVM system${NC}"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check for root/sudo
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root or with sudo${NC}"
    exit 1
fi

# PiKVM uses read-only filesystem by default
echo "Remounting filesystem as read-write..."
rw || mount -o remount,rw / 2>/dev/null || true

# Install directory
INSTALL_DIR="/opt/pyslirp"
echo "Installing to $INSTALL_DIR..."

# Create installation directory
mkdir -p "$INSTALL_DIR"

# Copy files
echo "Copying PyLiRP files..."
cp -r . "$INSTALL_DIR/"
cd "$INSTALL_DIR"

# Install Python dependencies
echo "Installing Python dependencies..."

# Check Python version
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo "Found Python $PYTHON_VERSION"
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_VERSION=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ $PYTHON_VERSION == 3.* ]]; then
        echo "Found Python $PYTHON_VERSION"
        PYTHON_CMD="python"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}Python 3 not found. Installing...${NC}"
    pacman -S --noconfirm python python-pip || apt-get install -y python3 python3-pip
    PYTHON_CMD="python3"
fi

# Create virtual environment
echo "Creating Python virtual environment..."
$PYTHON_CMD -m venv .venv

# Activate venv and install requirements
echo "Installing Python packages..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Check for USB gadget serial device
echo "Checking for USB gadget serial device..."
if [ -c /dev/ttyGS0 ]; then
    echo -e "${GREEN}✓ Found /dev/ttyGS0${NC}"
else
    echo -e "${YELLOW}⚠ /dev/ttyGS0 not found${NC}"
    echo "  This device will be created when USB gadget is configured"
    echo "  You may need to enable USB serial gadget in kvmd config"
fi

# Add kvmd user to dialout group (if exists)
if id "kvmd" &>/dev/null; then
    echo "Adding kvmd user to serial groups..."
    usermod -a -G dialout kvmd 2>/dev/null || true
    usermod -a -G tty kvmd 2>/dev/null || true
fi

# Set permissions
echo "Setting permissions..."
chown -R kvmd:kvmd "$INSTALL_DIR" 2>/dev/null || chown -R root:root "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/main.py"

# Install systemd service
echo "Installing systemd service..."
cp pyslirp-pikvm.service /etc/systemd/system/
systemctl daemon-reload

# Create log directory
mkdir -p /var/log
touch /var/log/pyslirp.log
chown kvmd:kvmd /var/log/pyslirp.log 2>/dev/null || true

# Enable USB gadget serial in kvmd (if config exists)
KVMD_CONFIG="/etc/kvmd/override.yaml"
if [ -f "$KVMD_CONFIG" ]; then
    echo "Checking kvmd configuration..."
    if ! grep -q "serial:" "$KVMD_CONFIG"; then
        echo -e "${YELLOW}Note: You may need to enable USB serial gadget in kvmd config${NC}"
        echo "Add to $KVMD_CONFIG:"
        echo "  otg:"
        echo "    devices:"
        echo "      serial:"
        echo "        enabled: true"
    fi
fi

# Create symlink for easy access
ln -sf "$INSTALL_DIR/main.py" /usr/local/bin/pyslirp 2>/dev/null || true

echo -e "${GREEN}=== Installation Complete ===${NC}"
echo ""
echo "Next steps:"
echo "1. Review configuration: $INSTALL_DIR/config_pikvm.yaml"
echo "2. Start the service: systemctl start pyslirp-pikvm"
echo "3. Enable at boot: systemctl enable pyslirp-pikvm"
echo "4. Check status: systemctl status pyslirp-pikvm"
echo "5. View logs: journalctl -u pyslirp-pikvm -f"
echo ""

# Check if we should start the service
read -p "Start PyLiRP service now? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl start pyslirp-pikvm
    sleep 2
    systemctl status pyslirp-pikvm --no-pager
fi

# Remount read-only if PiKVM
if [ -f /etc/kvmd/main.yaml ]; then
    echo "Remounting filesystem as read-only..."
    ro || mount -o remount,ro / 2>/dev/null || true
fi

echo -e "${GREEN}Done!${NC}"