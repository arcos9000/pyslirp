#!/bin/bash
# Clean up configuration file mess from previous installations

echo "PyLiRP Configuration Cleanup Script"
echo "==================================="
echo ""
echo "This script fixes configuration file conflicts by removing"
echo "template config files from the installation directory."
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

INSTALL_DIR="/opt/pyslirp"
CONFIG_DIR="/etc/pyslirp"

if [[ ! -d "$INSTALL_DIR" ]]; then
    echo "PyLiRP not found in $INSTALL_DIR - nothing to clean up"
    exit 0
fi

echo "Found PyLiRP installation in $INSTALL_DIR"
echo ""

# Show current config files
echo "Current configuration files:"
echo "============================"
echo "Install directory:"
ls -la "$INSTALL_DIR"/*.yaml 2>/dev/null || echo "  No YAML files found"
echo ""
echo "Config directory:"
ls -la "$CONFIG_DIR"/*.yaml 2>/dev/null || echo "  No YAML files found"
echo ""

# Check for the problematic config.yaml in install dir
if [[ -f "$INSTALL_DIR/config.yaml" ]]; then
    echo "⚠️  Found config.yaml in install directory - this can cause conflicts!"
    echo "   Install dir config: $INSTALL_DIR/config.yaml"
    echo "   Actual config:      $CONFIG_DIR/config.yaml"
    echo ""
    
    # Show the differences
    if [[ -f "$CONFIG_DIR/config.yaml" ]]; then
        echo "Checking for differences..."
        if diff -q "$INSTALL_DIR/config.yaml" "$CONFIG_DIR/config.yaml" >/dev/null; then
            echo "✓ Files are identical - safe to remove install dir copy"
        else
            echo "⚠️  Files are different!"
            echo "   This might explain configuration conflicts"
            echo ""
            echo "Port settings:"
            echo "  Install dir: $(grep -A1 'serial:' "$INSTALL_DIR/config.yaml" | grep 'port:' | head -1)"
            echo "  Config dir:  $(grep -A1 'serial:' "$CONFIG_DIR/config.yaml" | grep 'port:' | head -1)"
        fi
    fi
    
    echo ""
    read -p "Remove $INSTALL_DIR/config.yaml? [Y/n]: " choice
    choice=${choice:-Y}
    
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        echo "Backing up and removing $INSTALL_DIR/config.yaml..."
        cp "$INSTALL_DIR/config.yaml" "$INSTALL_DIR/config.yaml.bak"
        rm "$INSTALL_DIR/config.yaml"
        echo "✓ Removed conflicting config file"
        echo "✓ Backup saved as $INSTALL_DIR/config.yaml.bak"
    else
        echo "Skipped removal"
    fi
else
    echo "✓ No conflicting config.yaml found in install directory"
fi

echo ""
echo "Cleanup complete!"
echo ""
echo "The service should now use: $CONFIG_DIR/config.yaml"
echo "Templates are available in: $INSTALL_DIR/config_*.yaml"
echo ""
echo "To verify, restart the service:"
echo "  systemctl restart pyslirp"
echo "  systemctl status pyslirp"