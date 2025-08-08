#!/bin/bash
# Debug and fix PiKVM serial permissions

echo "=== PiKVM Serial Permission Debug ==="
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

echo "1. Checking serial device permissions:"
echo "----------------------------------------"
ls -la /dev/tty* | grep -E "(ttyUSB|ttyACM|ttyGS|ttyAMA)" || echo "No serial devices found"

echo ""
echo "2. Checking pyslirp user:"
echo "------------------------"
if id pyslirp &>/dev/null; then
    echo "✓ pyslirp user exists"
    echo "UID: $(id -u pyslirp)"
    echo "GID: $(id -g pyslirp)"
    echo "Groups: $(groups pyslirp)"
else
    echo "✗ pyslirp user does not exist!"
    exit 1
fi

echo ""
echo "3. Checking available groups:"
echo "----------------------------"
echo "All groups that pyslirp belongs to:"
id pyslirp

echo ""
echo "Available serial groups:"
getent group | grep -E "(dialout|uucp|serial|tty|root)" | cut -d: -f1

echo ""
echo "4. Testing direct access to /dev/ttyGS0:"
echo "----------------------------------------"
if [[ -c /dev/ttyGS0 ]]; then
    echo "✓ /dev/ttyGS0 exists"
    echo "Permissions: $(ls -la /dev/ttyGS0)"
    
    # Try different permission fixes
    echo ""
    echo "Attempting fixes..."
    
    # Method 1: Add to dialout group if it exists
    if getent group dialout >/dev/null; then
        echo "Adding pyslirp to dialout group..."
        usermod -a -G dialout pyslirp
        echo "New groups: $(groups pyslirp)"
    fi
    
    # Method 2: Add to tty group if it exists
    if getent group tty >/dev/null; then
        echo "Adding pyslirp to tty group..."
        usermod -a -G tty pyslirp
        echo "New groups: $(groups pyslirp)"
    fi
    
    # Method 3: Change device permissions directly
    echo "Setting device permissions..."
    chown root:dialout /dev/ttyGS0 2>/dev/null || chown root:tty /dev/ttyGS0 2>/dev/null || chown root:root /dev/ttyGS0
    chmod 666 /dev/ttyGS0  # More permissive for testing
    
    echo "New permissions: $(ls -la /dev/ttyGS0)"
    
    # Method 4: Test with Python as pyslirp user
    echo ""
    echo "Testing Python serial access as pyslirp user..."
    sudo -u pyslirp python3 -c "
import os, sys
print(f'Running as UID: {os.getuid()}, GID: {os.getgid()}')
print(f'Groups: {os.getgroups()}')
try:
    import serial
    print('✓ pyserial module imported')
    s = serial.Serial('/dev/ttyGS0', 115200, timeout=1)
    print('✓ Serial port opened successfully!')
    s.close()
    print('✓ Serial port closed successfully!')
except ImportError as e:
    print(f'✗ pyserial not installed: {e}')
    sys.exit(1)
except Exception as e:
    print(f'✗ Serial access failed: {e}')
    print('This indicates a permission issue')
    sys.exit(1)
" || echo "Python test failed"
    
else
    echo "✗ /dev/ttyGS0 does not exist"
    echo "Available tty devices:"
    ls -la /dev/tty* | head -20
fi

echo ""
echo "5. Creating persistent udev rule:"
echo "--------------------------------"
cat > /etc/udev/rules.d/99-pyslirp-ttygs.rules << 'EOF'
# PyLiRP PiKVM USB Gadget Serial Rules
# Make ttyGS* devices accessible to dialout and tty groups
SUBSYSTEM=="tty", KERNEL=="ttyGS*", GROUP="dialout", MODE="0666"
SUBSYSTEM=="tty", KERNEL=="ttyGS*", GROUP="tty", MODE="0666"
EOF

echo "Created udev rule:"
cat /etc/udev/rules.d/99-pyslirp-ttygs.rules

# Reload udev
if command -v udevadm >/dev/null; then
    echo "Reloading udev rules..."
    udevadm control --reload-rules
    udevadm trigger --subsystem-match=tty
fi

echo ""
echo "6. Final status check:"
echo "---------------------"
echo "pyslirp user groups: $(groups pyslirp)"
echo "/dev/ttyGS0 permissions: $(ls -la /dev/ttyGS0 2>/dev/null || echo 'Device not found')"

echo ""
echo "=== RECOMMENDATIONS ==="
echo ""
if [[ -c /dev/ttyGS0 ]]; then
    echo "1. Restart pyslirp service: systemctl restart pyslirp"
    echo "2. If still failing, try rebooting to ensure all permission changes take effect"
    echo "3. Check logs: journalctl -u pyslirp -f"
    echo ""
    echo "Alternative test commands:"
    echo "sudo -u pyslirp ls -la /dev/ttyGS0"
    echo "sudo -u pyslirp python3 -c 'import serial; serial.Serial(\"/dev/ttyGS0\", 115200, timeout=1).close()'"
else
    echo "ERROR: /dev/ttyGS0 not found on this system"
    echo "This might not be a PiKVM or the USB gadget isn't configured"
fi