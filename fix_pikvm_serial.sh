#!/bin/bash
# Fix PiKVM serial device permissions for PyLiRP

echo "Fixing PiKVM serial device permissions..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

# Check current serial device permissions
echo "Current serial device permissions:"
ls -la /dev/tty* | grep -E "(ttyUSB|ttyACM|ttyGS|ttyAMA)" || echo "No serial devices found"

echo ""
echo "Checking pyslirp user and groups:"
if id pyslirp &>/dev/null; then
    echo "pyslirp user exists"
    echo "Groups: $(groups pyslirp)"
else
    echo "ERROR: pyslirp user does not exist"
    exit 1
fi

# Detect serial groups on the system
echo ""
echo "Available serial-related groups:"
getent group | grep -E "(dialout|uucp|serial|tty)" || echo "No standard serial groups found"

# Find the appropriate group for serial access
SERIAL_GROUP=""
for group in "dialout" "uucp" "serial" "tty"; do
    if getent group "$group" &>/dev/null; then
        SERIAL_GROUP="$group"
        echo "Found serial group: $group"
        break
    fi
done

if [[ -z "$SERIAL_GROUP" ]]; then
    echo "Creating dialout group..."
    groupadd dialout
    SERIAL_GROUP="dialout"
fi

# Add pyslirp user to the serial group
echo "Adding pyslirp user to $SERIAL_GROUP group..."
usermod -a -G "$SERIAL_GROUP" pyslirp

# Fix permissions on ttyGS0 specifically for PiKVM
if [[ -c /dev/ttyGS0 ]]; then
    echo "Setting permissions for /dev/ttyGS0..."
    chown root:$SERIAL_GROUP /dev/ttyGS0
    chmod 660 /dev/ttyGS0
    echo "Fixed /dev/ttyGS0 permissions:"
    ls -la /dev/ttyGS0
else
    echo "WARNING: /dev/ttyGS0 not found"
fi

# Create udev rule for persistent ttyGS* permissions
echo "Creating udev rule for ttyGS* devices..."
cat > /etc/udev/rules.d/99-pikvm-ttygs.rules << EOF
# PiKVM USB Gadget Serial Device Rules
# Allow members of $SERIAL_GROUP to access ttyGS devices
SUBSYSTEM=="tty", KERNEL=="ttyGS*", GROUP="$SERIAL_GROUP", MODE="0660"
EOF

# Reload udev rules
if command -v udevadm &>/dev/null; then
    echo "Reloading udev rules..."
    udevadm control --reload-rules
    udevadm trigger
else
    echo "WARNING: udevadm not found, you may need to reboot"
fi

# Update the config file to use the correct serial port
echo ""
echo "Updating PyLiRP configuration..."
if [[ -f /etc/pyslirp/config.yaml ]]; then
    # Check what serial device to use
    SERIAL_DEVICE=""
    if [[ -c /dev/ttyGS0 ]]; then
        SERIAL_DEVICE="/dev/ttyGS0"
    elif [[ -c /dev/ttyUSB0 ]]; then
        SERIAL_DEVICE="/dev/ttyUSB0"
    elif [[ -c /dev/ttyAMA0 ]]; then
        SERIAL_DEVICE="/dev/ttyAMA0"
    else
        echo "WARNING: No suitable serial device found"
        echo "Available devices:"
        ls -la /dev/tty* | grep -E "(ttyUSB|ttyACM|ttyGS|ttyAMA)"
    fi
    
    if [[ -n "$SERIAL_DEVICE" ]]; then
        echo "Setting serial port to: $SERIAL_DEVICE"
        sed -i "s|port:.*|port: $SERIAL_DEVICE|" /etc/pyslirp/config.yaml
    fi
else
    echo "ERROR: /etc/pyslirp/config.yaml not found"
fi

echo ""
echo "Serial permission fix complete!"
echo ""
echo "Summary:"
echo "  - pyslirp user added to '$SERIAL_GROUP' group"
echo "  - /dev/ttyGS0 permissions fixed (if present)"
echo "  - udev rule created for persistent permissions"
echo "  - Configuration updated"
echo ""
echo "Next steps:"
echo "  1. Restart the service: systemctl restart pyslirp"
echo "  2. Check status: systemctl status pyslirp"
echo "  3. View logs: journalctl -u pyslirp -f"
echo ""
echo "If still having issues, try:"
echo "  - Reboot to ensure udev rules take effect"
echo "  - Check available serial devices: ls -la /dev/tty*"
echo "  - Test access manually: sudo -u pyslirp python3 -c \"import serial; s=serial.Serial('$SERIAL_DEVICE', 115200); print('Success'); s.close()\""