#!/bin/bash
# Fix PyLiRP for PiKVM read-only filesystem

echo "Fixing PyLiRP for PiKVM read-only filesystem..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

# Check if we have the PiKVM config
if [[ ! -f "config_pikvm.yaml" ]]; then
    echo "Error: config_pikvm.yaml not found"
    echo "Make sure you're running this from the pyslirp directory"
    exit 1
fi

# Backup existing config
if [[ -f /etc/pyslirp/config.yaml ]]; then
    echo "Backing up existing config to /etc/pyslirp/config.yaml.bak"
    cp /etc/pyslirp/config.yaml /etc/pyslirp/config.yaml.bak
fi

# Install PiKVM-specific config
echo "Installing PiKVM-compatible configuration..."
cp config_pikvm.yaml /etc/pyslirp/config.yaml

# Fix permissions
SERIAL_GROUP=$(groups pyslirp 2>/dev/null | cut -d: -f2 | tr ' ' '\n' | grep -E 'dialout|uucp|serial|tty' | head -1)
if [[ -z "$SERIAL_GROUP" ]]; then
    SERIAL_GROUP="dialout"
fi

chown root:$SERIAL_GROUP /etc/pyslirp/config.yaml
chmod 640 /etc/pyslirp/config.yaml

echo "Configuration updated for read-only filesystem!"
echo ""
echo "Key changes:"
echo "  - File logging: DISABLED (uses systemd journal only)"
echo "  - Packet capture: DISABLED (incompatible with read-only filesystem)"
echo "  - Console logging: ENABLED (goes to systemd journal)"
echo "  - Metrics: ENABLED (available at http://localhost:9090/metrics)"
echo ""
echo "To complete the fix:"
echo "  1. Edit /etc/pyslirp/config.yaml and set your serial port"
echo "  2. Restart service: systemctl restart pyslirp"
echo "  3. Check status: systemctl status pyslirp"
echo "  4. View logs: journalctl -u pyslirp -f"
echo ""
echo "If you need file logging, mount /var/log/pyslirp as tmpfs first:"
echo "  sudo mkdir -p /var/log/pyslirp"
echo "  sudo mount -t tmpfs -o size=100M tmpfs /var/log/pyslirp"
echo "  sudo chown pyslirp:$SERIAL_GROUP /var/log/pyslirp"
echo "  Then re-enable file logging in config.yaml"