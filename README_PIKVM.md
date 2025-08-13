# PyLiRP for PiKVM

This document provides specific instructions for deploying PyLiRP on PiKVM systems to enable PPP-over-serial access to PiKVM services.

## Overview

PyLiRP enables remote access to PiKVM through a serial connection using PPP (Point-to-Point Protocol). This is useful for:
- Out-of-band management when network access is unavailable
- Secure isolated access through serial console
- Emergency recovery scenarios
- Air-gapped environments

## Features

- ✅ **Completely userspace** - No root required after installation
- ✅ **No kernel modules** - Works with PiKVM's read-only filesystem
- ✅ **USB gadget support** - Uses PiKVM's `/dev/ttyGS0` serial device
- ✅ **Service integration** - Runs as systemd service with kvmd user
- ✅ **Multiple services** - Access SSH, web UI, and other PiKVM services

## Quick Installation

```bash
# Download and run PiKVM installer
sudo ./install_pikvm.sh
```

## Manual Installation

### 1. Prerequisites

Ensure your PiKVM has USB serial gadget enabled:

Edit `/etc/kvmd/override.yaml`:
```yaml
otg:
  devices:
    serial:
      enabled: true
```

Then restart kvmd:
```bash
sudo systemctl restart kvmd
```

### 2. Install PyLiRP

```bash
# Remount filesystem as read-write
rw

# Create installation directory
sudo mkdir -p /opt/pyslirp
sudo cp -r * /opt/pyslirp/
cd /opt/pyslirp

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set permissions
sudo chown -R kvmd:kvmd /opt/pyslirp

# Install service
sudo cp pyslirp-pikvm.service /etc/systemd/system/
sudo systemctl daemon-reload

# Remount read-only
ro
```

### 3. Configuration

The PiKVM-specific configuration is in `config_pikvm.yaml`:

```yaml
serial:
  port: /dev/ttyGS0  # USB gadget serial device
  baudrate: 115200

services:
  22:    # SSH access
    enabled: true
    host: "127.0.0.1"
    port: 22
  80:    # Web UI
    enabled: true
    host: "127.0.0.1"
    port: 80
  443:   # Web UI HTTPS
    enabled: true
    host: "127.0.0.1"
    port: 443
```

### 4. Start Service

```bash
# Start the service
sudo systemctl start pyslirp-pikvm

# Enable at boot
sudo systemctl enable pyslirp-pikvm

# Check status
sudo systemctl status pyslirp-pikvm

# View logs
sudo journalctl -u pyslirp-pikvm -f
```

## Client Setup

On the client machine (the one connecting TO the PiKVM):

### 1. Physical Connection

Connect a USB-to-serial cable:
- PiKVM USB port → USB-to-serial adapter → Client computer

### 2. Run PyLiRP Client

```bash
# Install PyLiRP on client
git clone https://github.com/arcos9000/pyslirp.git
cd pyslirp
./install_linux_venv.sh

# Configure serial port (edit config.yaml)
# Set serial port to your USB-serial device (e.g., /dev/ttyUSB0)

# Run in client mode
python3 main.py --mode client --config config.yaml
```

### 3. Access PiKVM Services

Once connected, access services through local ports:

```bash
# SSH to PiKVM
ssh kvmd@localhost -p 2222

# Access web UI (use SSH tunnel)
ssh -L 8080:localhost:80 kvmd@localhost -p 2222
# Then browse to http://localhost:8080
```

## Troubleshooting

### USB Gadget Not Found

If `/dev/ttyGS0` doesn't exist:

1. Check kvmd override config has serial enabled
2. Restart kvmd: `sudo systemctl restart kvmd`
3. Check dmesg: `dmesg | grep gadget`

### Permission Denied on Serial Port

```bash
# Add kvmd to required groups
sudo usermod -a -G dialout,tty kvmd

# Set device permissions
sudo chmod 666 /dev/ttyGS0
```

### Connection Not Establishing

1. Check both sides are running:
   - PiKVM: `systemctl status pyslirp-pikvm`
   - Client: Check PyLiRP client is running

2. Verify serial settings match on both sides:
   - Baudrate: 115200
   - 8N1 (8 data bits, no parity, 1 stop bit)

3. Test serial connection:
   ```bash
   # On PiKVM
   echo "TEST" > /dev/ttyGS0
   
   # On client
   cat /dev/ttyUSB0
   ```

### Service Fails to Start

Check logs:
```bash
sudo journalctl -u pyslirp-pikvm -n 50
```

Common issues:
- Python dependencies missing: Re-run installation
- Serial device not ready: Service will retry
- Read-only filesystem: Remount with `rw` command

## Performance Tuning

For optimal performance on PiKVM:

1. **Increase MTU** in `config_pikvm.yaml`:
   ```yaml
   ppp:
     mtu: 1500  # Maximum for better throughput
   ```

2. **Adjust buffer sizes**:
   ```yaml
   performance:
     read_buffer_size: 65536
     write_buffer_size: 65536
   ```

3. **Enable compression** (if CPU allows):
   ```yaml
   ppp:
     compression: true  # Future feature
   ```

## Security Considerations

1. **Access Control**: Configure IP allowlist in `config_pikvm.yaml`
2. **Rate Limiting**: Enabled by default to prevent DoS
3. **Service Isolation**: Only expose necessary services
4. **Encrypted Tunnel**: Use SSH for all connections

## Integration with PiKVM

PyLiRP integrates seamlessly with PiKVM:

- Runs as `kvmd` user
- Respects read-only filesystem
- Compatible with PiKVM's USB gadget mode
- Can be monitored through PiKVM web interface (logs)

## Support

- GitHub Issues: https://github.com/arcos9000/pyslirp/issues
- PiKVM Discord: Ask in #support channel
- Documentation: See main README.md for protocol details

## License

MIT License - See LICENSE file for details