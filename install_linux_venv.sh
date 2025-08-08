#!/bin/bash
set -e

# PyLiRP Linux Installation Script with Virtual Environment Support
# Handles Python version requirements and virtual environment creation
# Works with or without sudo, preserving virtual environment usage

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/pyslirp"
CONFIG_DIR="/etc/pyslirp"
LOG_DIR="/var/log/pyslirp"
USER="pyslirp"
GROUP=""  # Will be detected dynamically
VENV_DIR="$INSTALL_DIR/.venv"
PYTHON_MIN_VERSION="3.8"

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
        print_error "This script must be run as root for system installation"
        print_status "Use: sudo $0"
        exit 1
    fi
}

# Function to compare version numbers
version_compare() {
    local version1=$1
    local version2=$2
    [[ $(printf '%s\n%s\n' "$version1" "$version2" | sort -V | head -n1) == "$version2" ]]
}

find_suitable_python() {
    print_status "Finding suitable Python installation..." >&2
    
    # List of Python executables to try in order of preference
    local python_candidates=(
        "python3.12" "python3.11" "python3.10" "python3.9" "python3.8"
        "python3" "python"
    )
    
    for python_cmd in "${python_candidates[@]}"; do
        if command -v "$python_cmd" &> /dev/null; then
            local python_version
            python_version=$($python_cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            
            if [[ -n "$python_version" ]] && version_compare "$python_version" "$PYTHON_MIN_VERSION"; then
                print_success "Found suitable Python: $python_cmd (version $python_version)" >&2
                echo "$python_cmd"
                return 0
            else
                print_warning "$python_cmd version $python_version is too old (need $PYTHON_MIN_VERSION+)" >&2
            fi
        fi
    done
    
    return 1
}

detect_distro() {
    # Detect Linux distribution and return distro info
    local distro=""
    local version=""
    local package_manager=""
    
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        distro="$ID"
        version="$VERSION_ID"
    elif [[ -f /etc/redhat-release ]]; then
        distro="rhel"
        version=$(cat /etc/redhat-release | sed 's/.*release \([0-9]\+\).*/\1/')
    elif [[ -f /etc/debian_version ]]; then
        distro="debian"
        version=$(cat /etc/debian_version)
    fi
    
    # Determine package manager
    if command -v apt-get &> /dev/null; then
        package_manager="apt"
    elif command -v dnf &> /dev/null; then
        package_manager="dnf"
    elif command -v yum &> /dev/null; then
        package_manager="yum"
    elif command -v pacman &> /dev/null; then
        package_manager="pacman"
    elif command -v zypper &> /dev/null; then
        package_manager="zypper"
    elif command -v apk &> /dev/null; then
        package_manager="apk"
    elif command -v emerge &> /dev/null; then
        package_manager="portage"
    elif command -v xbps-install &> /dev/null; then
        package_manager="xbps"
    elif command -v pkg &> /dev/null; then
        package_manager="freebsd-pkg"
    else
        package_manager="unknown"
    fi
    
    echo "$distro|$version|$package_manager"
}

install_python_packages_by_distro() {
    local distro_info
    distro_info=$(detect_distro)
    IFS='|' read -ra DISTRO_PARTS <<< "$distro_info"
    local distro="${DISTRO_PARTS[0]}"
    local version="${DISTRO_PARTS[1]}"
    local pkg_mgr="${DISTRO_PARTS[2]}"
    
    print_status "Detected: $distro $version (package manager: $pkg_mgr)"
    
    case "$pkg_mgr" in
        "apt")
            # Debian/Ubuntu family
            print_status "Installing Python packages via APT..."
            apt-get update
            case "$distro" in
                "ubuntu")
                    if [[ "${version%%.*}" -ge 20 ]]; then
                        apt-get install -y python3 python3-pip python3-venv python3-dev build-essential
                    else
                        apt-get install -y python3 python3-pip python3-venv python3-dev python3-setuptools build-essential
                    fi
                    ;;
                "debian")
                    if [[ "${version%%.*}" -ge 10 ]]; then
                        apt-get install -y python3 python3-pip python3-venv python3-dev build-essential
                    else
                        apt-get install -y python3 python3-pip python3-venv python3-dev python3-setuptools build-essential
                    fi
                    ;;
                *)
                    apt-get install -y python3 python3-pip python3-venv python3-dev build-essential
                    ;;
            esac
            ;;
            
        "dnf")
            # Fedora, newer RHEL/CentOS
            print_status "Installing Python packages via DNF..."
            dnf install -y python3 python3-pip python3-venv python3-devel gcc
            ;;
            
        "yum")
            # Older RHEL/CentOS
            print_status "Installing Python packages via YUM..."
            yum install -y epel-release || true  # Enable EPEL if available
            yum install -y python3 python3-pip python3-venv python3-devel gcc
            ;;
            
        "pacman")
            # Arch Linux family
            print_status "Installing Python packages via Pacman..."
            pacman -Sy --noconfirm python python-pip python-virtualenv base-devel
            ;;
            
        "zypper")
            # openSUSE family
            print_status "Installing Python packages via Zypper..."
            zypper refresh
            zypper install -y python3 python3-pip python3-venv python3-devel gcc
            ;;
            
        "apk")
            # Alpine Linux
            print_status "Installing Python packages via APK..."
            apk update
            apk add python3 python3-dev py3-pip py3-virtualenv build-base
            ;;
            
        "portage")
            # Gentoo
            print_status "Installing Python packages via Portage..."
            emerge --sync
            emerge dev-lang/python:3.8 dev-python/pip dev-python/virtualenv
            ;;
            
        "xbps")
            # Void Linux
            print_status "Installing Python packages via XBPS..."
            xbps-install -Sy python3 python3-pip python3-venv python3-devel
            ;;
            
        "freebsd-pkg")
            # FreeBSD
            print_status "Installing Python packages via PKG..."
            pkg update
            pkg install -y python38 py38-pip py38-virtualenv
            ;;
            
        *)
            print_error "Unsupported package manager: $pkg_mgr"
            print_error "Detected distro: $distro $version"
            print_error ""
            print_error "Please install Python 3.8+ manually with these packages:"
            print_error "- python3 (>= 3.8)"
            print_error "- python3-pip"
            print_error "- python3-venv"
            print_error "- python3-dev (development headers)"
            print_error "- build tools (gcc, make, etc.)"
            exit 1
            ;;
    esac
}

install_python_if_needed() {
    print_status "Checking Python installation requirements..." >&2
    
    local python_cmd
    python_cmd=$(find_suitable_python)
    
    if [[ $? -ne 0 ]]; then
        print_warning "No suitable Python found. Attempting to install Python 3.8+" >&2
        
        # Install Python using distro-specific method
        install_python_packages_by_distro
        
        # Verify installation
        python_cmd=$(find_suitable_python)
        if [[ $? -ne 0 ]]; then
            print_error "Failed to install suitable Python version" >&2
            print_error "Please install Python 3.8+ manually and try again" >&2
            exit 1
        fi
    fi
    
    echo "$python_cmd"
}

create_virtual_environment() {
    local python_cmd=$1
    print_status "Creating virtual environment with $python_cmd..."
    
    # Create venv directory if it doesn't exist
    mkdir -p "$(dirname "$VENV_DIR")"
    
    # Remove existing venv if it exists and is broken
    if [[ -d "$VENV_DIR" ]]; then
        if ! "$VENV_DIR/bin/python" -c "import sys" &>/dev/null; then
            print_warning "Existing virtual environment is broken, recreating..."
            rm -rf "$VENV_DIR"
        fi
    fi
    
    # Create new virtual environment if needed
    if [[ ! -d "$VENV_DIR" ]]; then
        print_status "Creating new virtual environment..."
        "$python_cmd" -m venv "$VENV_DIR"
        
        if [[ $? -ne 0 ]]; then
            print_error "Failed to create virtual environment"
            exit 1
        fi
    fi
    
    # Verify virtual environment
    if [[ ! -f "$VENV_DIR/bin/python" ]]; then
        print_error "Virtual environment creation failed - python executable not found"
        exit 1
    fi
    
    # Test virtual environment
    local venv_version
    venv_version=$("$VENV_DIR/bin/python" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    
    if [[ -z "$venv_version" ]]; then
        print_error "Virtual environment python is not working"
        exit 1
    fi
    
    print_success "Virtual environment created with Python $venv_version"
    print_success "Virtual environment path: $VENV_DIR"
}

install_python_packages_venv() {
    print_status "Installing Python packages in virtual environment..."
    
    local venv_python="$VENV_DIR/bin/python"
    local venv_pip="$VENV_DIR/bin/pip"
    
    # Verify virtual environment is working
    if [[ ! -x "$venv_python" ]]; then
        print_error "Virtual environment Python not found or not executable: $venv_python"
        exit 1
    fi
    
    # Upgrade pip in virtual environment
    print_status "Upgrading pip in virtual environment..."
    "$venv_python" -m pip install --upgrade pip
    
    if [[ $? -ne 0 ]]; then
        print_error "Failed to upgrade pip in virtual environment"
        exit 1
    fi
    
    # Install base requirements
    if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
        print_status "Installing base requirements..."
        "$venv_pip" install -r "$SCRIPT_DIR/requirements.txt"
        
        if [[ $? -ne 0 ]]; then
            print_error "Failed to install base requirements"
            exit 1
        fi
    else
        print_warning "requirements.txt not found, installing minimal dependencies"
        "$venv_pip" install pyserial pyserial-asyncio pyyaml
    fi
    
    # Install additional packages that might be needed
    print_status "Installing additional Python packages..."
    "$venv_pip" install psutil prometheus-client || print_warning "Some optional packages failed to install"
    
    print_success "Python packages installed in virtual environment"
    
    # Verify key packages
    print_status "Verifying package installation..."
    local packages=("serial" "serial_asyncio" "yaml")
    for package in "${packages[@]}"; do
        if "$venv_python" -c "import $package" 2>/dev/null; then
            print_success "✓ $package"
        else
            print_error "✗ $package failed to import"
            exit 1
        fi
    done
}

detect_serial_group() {
    # Detect the appropriate group for serial port access
    local serial_groups=("dialout" "uucp" "serial" "tty")
    
    for group in "${serial_groups[@]}"; do
        if getent group "$group" &>/dev/null; then
            echo "$group"
            return 0
        fi
    done
    
    # If no standard serial group exists, create dialout
    print_warning "No standard serial group found, creating 'dialout' group"
    groupadd dialout
    echo "dialout"
    return 0
}

create_user() {
    print_status "Creating system user..."
    
    # Detect appropriate serial group
    local serial_group
    serial_group=$(detect_serial_group)
    
    print_status "Using serial group: $serial_group"
    
    # Create pyslirp user if it doesn't exist
    if ! id "$USER" &>/dev/null; then
        useradd -r -s /bin/false -d "$INSTALL_DIR" -c "PyLiRP Service User" "$USER"
        print_success "Created user: $USER"
    else
        print_status "User $USER already exists"
    fi
    
    # Add user to serial group for serial port access
    usermod -a -G "$serial_group" "$USER"
    print_success "Added $USER to $serial_group group"
    
    # Store the group for later use
    GROUP="$serial_group"
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
    # Config dir owned by root but readable by group
    chown root:$GROUP "$CONFIG_DIR"
    
    chmod 755 "$INSTALL_DIR"
    chmod 755 "$CONFIG_DIR"  # Make directory accessible
    chmod 755 "$LOG_DIR"
    chmod 755 /var/run/pyslirp
    
    print_success "Directories created"
}

select_deployment_mode() {
    print_status "Configuring deployment mode..."
    
    echo
    echo "Please select your PyLiRP deployment mode:"
    echo
    echo "1. HOST ONLY    - Expose local services to remote clients"
    echo "                  (Remote clients connect to YOUR services)"
    echo
    echo "2. CLIENT ONLY  - Connect to remote services"
    echo "                  (YOU connect to remote services on non-conflicting ports)"
    echo
    echo "3. HYBRID       - Both host and client (automatic +10000 port offset)"
    echo "                  (Bidirectional access - best for most users)"
    echo
    
    while true; do
        read -p "Select deployment mode [1-3]: " choice
        case $choice in
            1)
                DEPLOYMENT_MODE="host"
                CONFIG_SOURCE="config_host.yaml"
                break
                ;;
            2)
                DEPLOYMENT_MODE="client" 
                CONFIG_SOURCE="config_client.yaml"
                break
                ;;
            3)
                DEPLOYMENT_MODE="hybrid"
                CONFIG_SOURCE="config_hybrid.yaml"
                break
                ;;
            *)
                echo "Please enter 1, 2, or 3"
                ;;
        esac
    done
    
    print_success "Selected: $DEPLOYMENT_MODE mode"
}

install_files() {
    print_status "Installing application files..."
    
    # Copy Python modules
    cp "$SCRIPT_DIR"/*.py "$INSTALL_DIR/"
    
    # Copy deployment configuration templates for reference (not the main config.yaml)
    cp "$SCRIPT_DIR"/config_*.yaml "$INSTALL_DIR/" 2>/dev/null || true
    cp "$SCRIPT_DIR"/configure_deployment.sh "$INSTALL_DIR/" 2>/dev/null || true
    
    # Install ONLY the selected configuration to /etc/pyslirp
    if [[ -f "$SCRIPT_DIR/$CONFIG_SOURCE" ]]; then
        cp "$SCRIPT_DIR/$CONFIG_SOURCE" "$CONFIG_DIR/config.yaml"
        print_success "Installed $DEPLOYMENT_MODE configuration"
    else
        # Fallback: create a default config from template
        print_warning "Deployment-specific config not found, creating default"
        cp "$SCRIPT_DIR"/config.yaml "$CONFIG_DIR/" 2>/dev/null || {
            print_error "No configuration files found!"
            exit 1
        }
    fi
    
    # Copy requirements files for reference
    if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
        cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
    fi
    
    # Set permissions
    chmod 644 "$INSTALL_DIR"/*.py
    # Config file should be readable by the pyslirp group
    chown root:$GROUP "$CONFIG_DIR"/config.yaml
    chmod 640 "$CONFIG_DIR"/config.yaml
    
    # Make main script executable (though we'll use the venv python)
    chmod +x "$INSTALL_DIR"/main.py
    
    print_success "Application files installed"
}

configure_udev_rules() {
    print_status "Configuring udev rules for serial ports..."
    
    cat > /etc/udev/rules.d/99-pyslirp-serial.rules << EOF
# PyLiRP Serial Port Rules
# Allow pyslirp user to access serial devices

# USB serial devices
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", GROUP="$GROUP", MODE="0660"
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", GROUP="$GROUP", MODE="0660"
SUBSYSTEM=="tty", ATTRS{idVendor}=="067b", GROUP="$GROUP", MODE="0660"

# Generic USB serial
SUBSYSTEM=="tty", KERNEL=="ttyUSB*", GROUP="$GROUP", MODE="0660"
SUBSYSTEM=="tty", KERNEL=="ttyACM*", GROUP="$GROUP", MODE="0660"
EOF
    
    # Reload udev rules
    if command -v udevadm &> /dev/null; then
        udevadm control --reload-rules
        udevadm trigger
        print_success "Udev rules configured for group: $GROUP"
    else
        print_warning "udevadm not found, udev rules created but not reloaded"
    fi
}

create_systemd_service() {
    print_status "Creating systemd service..."
    
    cat > /etc/systemd/system/pyslirp.service << EOF
[Unit]
Description=PyLiRP - Python SLiRP PPP Bridge
After=network.target

[Service]
Type=simple
User=$USER
Group=$GROUP
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$VENV_DIR/bin:\$PATH
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/main.py --config $CONFIG_DIR/config.yaml
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pyslirp

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$LOG_DIR /var/run/pyslirp $CONFIG_DIR
DeviceAllow=/dev/tty* rw
DeviceAllow=/dev/serial* rw

[Install]
WantedBy=multi-user.target
EOF
    
    chmod 644 /etc/systemd/system/pyslirp.service
    print_success "Systemd service created"
}

create_wrapper_scripts() {
    print_status "Creating wrapper scripts..."
    
    # Create main wrapper script
    cat > /usr/local/bin/pyslirp << EOF
#!/bin/bash
# PyLiRP Wrapper Script - ensures virtual environment is used
cd "$INSTALL_DIR"
exec "$VENV_DIR/bin/python" "$INSTALL_DIR/main.py" "\$@"
EOF
    
    chmod +x /usr/local/bin/pyslirp
    
    # Create status script
    cat > /usr/local/bin/pyslirp-status << 'EOF'
#!/bin/bash
# PyLiRP Status Script

echo "=== PyLiRP Service Status ==="
systemctl status pyslirp.service --no-pager

echo -e "\n=== Virtual Environment Info ==="
if [[ -f "$VENV_DIR/bin/python" ]]; then
    echo "Virtual environment: $VENV_DIR"
    echo "Python version: $($VENV_DIR/bin/python --version)"
    echo "Pip packages:"
    $VENV_DIR/bin/pip list | grep -E "(serial|yaml|psutil)" || echo "Core packages status unknown"
else
    echo "Virtual environment not found: $VENV_DIR"
fi

echo -e "\n=== Connection Information ==="
if systemctl is-active pyslirp.service >/dev/null 2>&1; then
    if command -v curl >/dev/null 2>&1; then
        echo "Metrics endpoint:"
        curl -s http://localhost:9090/metrics | head -10 || echo "Metrics not available"
    else
        echo "curl not available for metrics check"
    fi
else
    echo "Service is not running"
fi

echo -e "\n=== Recent Log Entries ==="
journalctl -u pyslirp.service --no-pager -n 10
EOF
    
    # Update the status script with actual venv path
    sed -i "s|\$VENV_DIR|$VENV_DIR|g" /usr/local/bin/pyslirp-status
    chmod +x /usr/local/bin/pyslirp-status
    
    # Create configuration validation script
    cat > /usr/local/bin/pyslirp-validate << EOF
#!/bin/bash
# PyLiRP Configuration Validation Script

echo "Validating PyLiRP configuration..."
cd "$INSTALL_DIR"

# Use the virtual environment python
"$VENV_DIR/bin/python" -c "
import sys
sys.path.insert(0, '.')
try:
    from config_manager import ConfigManager
    config_manager = ConfigManager()
    config = config_manager.load_config('$CONFIG_DIR/config.yaml')
    print('✓ Configuration is valid')
    print(f'✓ Serial port: {config.serial.port}')
    print(f'✓ Services configured: {len([s for s in config.services.values() if s.enabled])}')
    print('✓ All checks passed')
    sys.exit(0)
except Exception as e:
    print(f'✗ Configuration error: {e}')
    sys.exit(1)
"
EOF
    
    chmod +x /usr/local/bin/pyslirp-validate
    
    print_success "Wrapper scripts created"
}

setup_systemd() {
    print_status "Setting up systemd service..."
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable service (but don't start yet)
    systemctl enable pyslirp.service
    
    print_success "Systemd service configured"
}

show_post_install_info() {
    print_success "PyLiRP installation with virtual environment completed!"
    
    echo
    echo "=== Installation Summary ==="
    echo "Install Directory: $INSTALL_DIR"
    echo "Virtual Environment: $VENV_DIR" 
    echo "Configuration: $CONFIG_DIR/config.yaml"
    echo "Deployment Mode: $DEPLOYMENT_MODE"
    echo "Logs: $LOG_DIR/"
    echo "Service User: $USER"
    echo "Serial Group: $GROUP"
    echo
    echo "=== Python Environment ==="
    local venv_version
    venv_version=$("$VENV_DIR/bin/python" --version 2>/dev/null)
    echo "Python Version: $venv_version"
    echo "Virtual Environment: $VENV_DIR"
    echo "Pip Location: $VENV_DIR/bin/pip"
    echo
    echo "=== Next Steps ==="
    echo "1. Edit configuration: $CONFIG_DIR/config.yaml"
    echo "2. Validate configuration: pyslirp-validate"
    echo "3. Start the service: systemctl start pyslirp"
    echo "4. Check status: pyslirp-status"
    echo "5. View logs: journalctl -u pyslirp -f"
    echo
    echo "=== Command Usage ==="
    echo "- Run directly: pyslirp [options]"
    echo "- Service control: systemctl {start|stop|restart} pyslirp"
    echo "- Check status: pyslirp-status"  
    echo "- Validate config: pyslirp-validate"
    echo
    echo "=== Virtual Environment Notes ==="
    echo "- All Python dependencies are isolated in: $VENV_DIR"
    echo "- Service automatically uses the virtual environment"
    echo "- Manual Python usage: $VENV_DIR/bin/python"
    echo "- Package management: $VENV_DIR/bin/pip"
    echo
    echo "=== Serial Port Access ==="
    echo "- Service runs as user '$USER' in group '$GROUP'"
    echo "- For manual testing, add your user to serial group:"
    echo "  sudo usermod -a -G $GROUP \$USER"
    echo "  (then logout and login again)"
    echo "- Check serial permissions: ls -l /dev/ttyUSB* /dev/ttyACM*"
    echo
    echo "=== Deployment Mode: $DEPLOYMENT_MODE ==="
    case "$DEPLOYMENT_MODE" in
        "host")
            echo "HOST MODE - Exposing local services to remote clients:"
            echo "- Remote clients can access your services:"
            echo "  SSH: port 22, HTTP: port 80, HTTPS: port 443"
            echo "- Make sure these services are running locally"
            ;;
        "client")
            echo "CLIENT MODE - Connecting to remote services:"
            echo "- Access remote services on these local ports:"
            echo "  Remote SSH: localhost:2222"
            echo "  Remote HTTP: localhost:8080"
            echo "  Remote HTTPS: localhost:8443"
            ;;
        "hybrid")
            echo "HYBRID MODE - Bidirectional access (+10000 offset):"
            echo "- Your local services: SSH:22, HTTP:80, HTTPS:443"
            echo "- Remote services: SSH:10022, HTTP:10080, HTTPS:10443"
            echo "- Example: ssh user@localhost -p 10022 (remote SSH)"
            ;;
    esac
    echo ""
    echo "=== Troubleshooting ==="
    echo "- If Python packages are missing, recreate venv: rm -rf $VENV_DIR && $0"
    echo "- Check virtual environment: $VENV_DIR/bin/python --version"
    echo "- List installed packages: $VENV_DIR/bin/pip list"
    echo "- Service logs: journalctl -u pyslirp -f"
    echo "- Serial group membership: groups $USER"
    echo "- Change deployment mode: $INSTALL_DIR/configure_deployment.sh"
}

# Main installation flow
main() {
    echo "PyLiRP Linux Installation Script with Virtual Environment Support"
    echo "==============================================================="
    
    check_root
    
    # Find and install suitable Python
    local python_cmd
    python_cmd=$(install_python_if_needed)
    
    create_user
    create_directories
    
    # Select deployment mode before installing files
    select_deployment_mode
    
    # Create virtual environment and install packages
    create_virtual_environment "$python_cmd"
    install_python_packages_venv
    
    install_files
    configure_udev_rules
    create_systemd_service
    create_wrapper_scripts
    setup_systemd
    show_post_install_info
}

# Check if script is being sourced or executed
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi