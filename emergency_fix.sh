#!/bin/bash
# Emergency fix for PiKVM serial permissions

echo "Emergency PiKVM serial permission fix"
echo "===================================="

if [[ $EUID -ne 0 ]]; then
   echo "Run as root: sudo $0"
   exit 1
fi

# Most aggressive fix - make device world-writable temporarily
if [[ -c /dev/ttyGS0 ]]; then
    echo "Setting world-writable permissions on /dev/ttyGS0..."
    chmod 666 /dev/ttyGS0
    chown root:root /dev/ttyGS0
    ls -la /dev/ttyGS0
    
    echo ""
    echo "Testing access as pyslirp user..."
    sudo -u pyslirp python3 -c "
import serial
try:
    s = serial.Serial('/dev/ttyGS0', 115200, timeout=1)
    print('SUCCESS: Can open /dev/ttyGS0')
    s.close()
except Exception as e:
    print(f'FAILED: {e}')
" || echo "Python test failed - pyserial might not be installed"
    
    echo ""
    echo "Restarting pyslirp service..."
    systemctl restart pyslirp
    sleep 2
    systemctl status pyslirp --no-pager
    
else
    echo "ERROR: /dev/ttyGS0 not found"
    echo "Available devices:"
    ls -la /dev/tty* | grep -E "tty(USB|ACM|GS|AMA)"
fi

echo ""
echo "If this works, check logs with: journalctl -u pyslirp -f"