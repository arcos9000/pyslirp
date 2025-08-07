#!/bin/bash
set -e

# PyLiRP Installation Script
# Installs Python SLiRP implementation with proper configuration

INSTALL_DIR="/opt/pyslirp"
CONFIG_DIR="/etc/pyslirp"
LOG_DIR="/var/log/pyslirp"
USER="pyslirp"
GROUP="dialout"

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

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root"
        exit 1
    fi
}

check_dependencies() {
    print_status "Checking dependencies..."
    
    # Check Python 3.8+
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [[ $(echo "$python_version < 3.8" | bc -l) -eq 1 ]]; then
        print_error "Python 3.8+ is required, found $python_version"
        exit 1
    fi
    
    print_success "Python $python_version found"
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        print_warning "pip3 not found, installing..."
        apt-get update && apt-get install -y python3-pip
    fi
    
    # Check systemd
    if ! command -v systemctl &> /dev/null; then
        print_warning "systemd not found, service management may not work"
    fi
    
    print_success "Dependencies checked"
}

install_python_packages() {
    print_status "Installing Python packages..."
    
    # Install required packages
    pip3 install --upgrade pip
    pip3 install -r requirements.txt
    
    print_success "Python packages installed"
}

create_user() {
    print_status "Creating system user..."
    
    # Create pyslirp user if it doesn't exist
    if ! id "$USER" &>/dev/null; then
        useradd -r -s /bin/false -d "$INSTALL_DIR" -c "PyLiRP Service User" "$USER"
        print_success "Created user: $USER"
    else
        print_status "User $USER already exists"
    fi
    
    # Add user to dialout group for serial port access
    usermod -a -G "$GROUP" "$USER"
    print_success "Added $USER to $GROUP group"
}

create_directories() {
    print_status "Creating directories..."
    
    # Create installation directory
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p /var/run/pyslirp
    
    # Set ownership and permissions
    chown -R "$USER:$GROUP" "$INSTALL_DIR"
    chown -R "$USER:$GROUP" "$LOG_DIR" 
    chown -R "$USER:$GROUP" /var/run/pyslirp
    chown root:root "$CONFIG_DIR"
    
    chmod 755 "$INSTALL_DIR"
    chmod 750 "$CONFIG_DIR"
    chmod 755 "$LOG_DIR"
    chmod 755 /var/run/pyslirp
    
    print_success "Directories created"
}

install_files() {
    print_status "Installing application files..."
    
    # Copy Python modules
    cp *.py "$INSTALL_DIR/"
    
    # Copy configuration files
    cp config.yaml "$CONFIG_DIR/"
    
    # Copy systemd service file
    cp pyslirp.service /etc/systemd/system/
    
    # Set permissions
    chmod 644 "$INSTALL_DIR"/*.py
    chmod 640 "$CONFIG_DIR"/config.yaml
    chmod 644 /etc/systemd/system/pyslirp.service
    
    # Make main script executable
    chmod +x "$INSTALL_DIR"/pySLiRP.py
    
    print_success "Application files installed"
}

create_default_config() {
    print_status "Creating default configuration..."
    
    # Create environment file
    cat > /etc/default/pyslirp << 'EOF'
# PyLiRP Environment Configuration
# Override configuration values here

# Serial port configuration
#PYSLIRP_SERIAL_PORT=/dev/ttyUSB0
#PYSLIRP_SERIAL_BAUDRATE=115200

# Network configuration  
#PYSLIRP_LOCAL_IP=10.0.0.1
#PYSLIRP_REMOTE_IP=10.0.0.2

# Logging configuration
#PYSLIRP_LOG_LEVEL=INFO
#PYSLIRP_LOG_FILE=/var/log/pyslirp/pyslirp.log

# SOCKS proxy (if needed)
#PYSLIRP_SOCKS_HOST=127.0.0.1
#PYSLIRP_SOCKS_PORT=1080

# Monitoring
#PYSLIRP_METRICS_PORT=9090
EOF
    
    chmod 644 /etc/default/pyslirp
    print_success "Default configuration created"
}

setup_logrotate() {
    print_status "Setting up log rotation..."
    
    cat > /etc/logrotate.d/pyslirp << 'EOF'
/var/log/pyslirp/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 pyslirp dialout
    postrotate
        systemctl reload pyslirp.service > /dev/null 2>&1 || true
    endscript
}
EOF
    
    print_success "Log rotation configured"
}

configure_udev_rules() {
    print_status "Configuring udev rules for serial ports..."
    
    cat > /etc/udev/rules.d/99-pyslirp-serial.rules << 'EOF'
# PyLiRP Serial Port Rules
# Allow pyslirp user to access serial devices

# USB serial devices
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", GROUP="dialout", MODE="0660"
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", GROUP="dialout", MODE="0660"
SUBSYSTEM=="tty", ATTRS{idVendor}=="067b", GROUP="dialout", MODE="0660"

# Generic USB serial
SUBSYSTEM=="tty", KERNEL=="ttyUSB*", GROUP="dialout", MODE="0660"
SUBSYSTEM=="tty", KERNEL=="ttyACM*", GROUP="dialout", MODE="0660"
EOF
    
    # Reload udev rules
    udevadm control --reload-rules
    udevadm trigger
    
    print_success "Udev rules configured"
}

setup_systemd() {
    print_status "Setting up systemd service..."
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable service (but don't start yet)
    systemctl enable pyslirp.service
    
    print_success "Systemd service configured"
}

create_helper_scripts() {
    print_status "Creating helper scripts..."
    
    # Create status script
    cat > /usr/local/bin/pyslirp-status << 'EOF'
#!/bin/bash
# PyLiRP Status Script

echo "=== PyLiRP Service Status ==="
systemctl status pyslirp.service --no-pager

echo -e "\n=== Connection Information ==="
if systemctl is-active pyslirp.service >/dev/null 2>&1; then
    if command -v curl >/dev/null 2>&1; then
        echo "Metrics endpoint:"
        curl -s http://localhost:9090/metrics | head -20 || echo "Metrics not available"
        
        echo -e "\nHealth status:"
        curl -s http://localhost:9091/health | python3 -m json.tool 2>/dev/null || echo "Health check not available"
    else
        echo "curl not available for metrics check"
    fi
else
    echo "Service is not running"
fi

echo -e "\n=== Recent Log Entries ==="
journalctl -u pyslirp.service --no-pager -n 10
EOF
    
    chmod +x /usr/local/bin/pyslirp-status
    
    # Create configuration validation script
    cat > /usr/local/bin/pyslirp-validate << 'EOF'
#!/bin/bash
# PyLiRP Configuration Validation Script

echo "Validating PyLiRP configuration..."
cd /opt/pyslirp
python3 -c "
import sys
sys.path.insert(0, '.')
from config_manager import load_config
try:
    config = load_config('/etc/pyslirp/config.yaml')
    print('✓ Configuration is valid')
    print(f'✓ Serial port: {config.serial.port}')
    print(f'✓ Services configured: {len(config.services)}')
    print('✓ All checks passed')
    sys.exit(0)
except Exception as e:
    print(f'✗ Configuration error: {e}')
    sys.exit(1)
"
EOF
    
    chmod +x /usr/local/bin/pyslirp-validate
    
    print_success "Helper scripts created"
}

perform_security_setup() {
    print_status "Applying security configurations..."
    
    # Set SELinux context if available
    if command -v setsebool >/dev/null 2>&1; then
        print_status "Configuring SELinux..."
        # Allow network connections (if needed)
        setsebool -P allow_user_exec_content 1 2>/dev/null || true
    fi
    
    # Set up firewall rules if ufw is available
    if command -v ufw >/dev/null 2>&1; then
        print_status "Configuring firewall for metrics..."
        ufw allow 9090/tcp comment "PyLiRP Metrics" || true
        ufw allow 9091/tcp comment "PyLiRP Health" || true
    fi
    
    print_success "Security configuration applied"
}

show_post_install_info() {
    print_success "PyLiRP installation completed!"
    
    echo
    echo "=== Next Steps ==="
    echo "1. Edit configuration file: $CONFIG_DIR/config.yaml"
    echo "2. Validate configuration: pyslirp-validate"
    echo "3. Start the service: systemctl start pyslirp"
    echo "4. Check status: pyslirp-status"
    echo "5. View logs: journalctl -u pyslirp -f"
    echo
    echo "=== Important Notes ==="
    echo "- Service runs as user '$USER' in group '$GROUP'"
    echo "- Serial devices must be accessible to '$GROUP' group"
    echo "- Configuration file: $CONFIG_DIR/config.yaml"
    echo "- Log files: $LOG_DIR/"
    echo "- Metrics endpoint: http://localhost:9090/metrics"
    echo "- Health endpoint: http://localhost:9091/health"
    echo
    echo "=== Configuration ==="
    echo "- Default config created in $CONFIG_DIR/config.yaml"
    echo "- Environment overrides: /etc/default/pyslirp"
    echo "- Service file: /etc/systemd/system/pyslirp.service"
    echo
    echo "=== Troubleshooting ==="
    echo "- Check serial permissions: ls -l /dev/ttyUSB*"
    echo "- Validate config: pyslirp-validate"
    echo "- Check service status: pyslirp-status"
    echo "- View detailed logs: journalctl -u pyslirp -f"
}

# Main installation flow
main() {
    echo "PyLiRP Installation Script"
    echo "========================="
    
    check_root
    check_dependencies
    create_user
    create_directories
    install_python_packages
    install_files
    create_default_config
    setup_logrotate
    configure_udev_rules
    setup_systemd
    create_helper_scripts
    perform_security_setup
    show_post_install_info
}

# Check if script is being sourced or executed
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi