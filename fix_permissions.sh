#!/bin/bash
# Fix PyLiRP permissions issue

echo "Fixing PyLiRP configuration permissions..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

# Fix config directory permissions
if [[ -d /etc/pyslirp ]]; then
    echo "Fixing /etc/pyslirp permissions..."
    
    # Make the directory readable by the pyslirp user
    chmod 755 /etc/pyslirp
    
    # Fix config.yaml permissions - make it readable by the pyslirp group
    if [[ -f /etc/pyslirp/config.yaml ]]; then
        # Detect the serial group that pyslirp user belongs to
        PYSLIRP_GROUP=$(groups pyslirp 2>/dev/null | cut -d: -f2 | tr ' ' '\n' | grep -E 'dialout|uucp|serial|tty' | head -1)
        
        if [[ -z "$PYSLIRP_GROUP" ]]; then
            PYSLIRP_GROUP="dialout"
            echo "Warning: Could not detect pyslirp user's serial group, using dialout"
        fi
        
        echo "Setting config.yaml ownership to root:$PYSLIRP_GROUP"
        chown root:$PYSLIRP_GROUP /etc/pyslirp/config.yaml
        chmod 640 /etc/pyslirp/config.yaml
        
        echo "Config permissions fixed:"
        ls -la /etc/pyslirp/config.yaml
    else
        echo "Error: /etc/pyslirp/config.yaml not found"
        echo "Creating default config from current directory..."
        
        if [[ -f config.yaml ]]; then
            cp config.yaml /etc/pyslirp/
            # Detect group as above
            PYSLIRP_GROUP=$(groups pyslirp 2>/dev/null | cut -d: -f2 | tr ' ' '\n' | grep -E 'dialout|uucp|serial|tty' | head -1)
            if [[ -z "$PYSLIRP_GROUP" ]]; then
                PYSLIRP_GROUP="dialout"
            fi
            chown root:$PYSLIRP_GROUP /etc/pyslirp/config.yaml
            chmod 640 /etc/pyslirp/config.yaml
            echo "Config file created and permissions set"
        else
            echo "Error: No config.yaml found in current directory"
            exit 1
        fi
    fi
else
    echo "Error: /etc/pyslirp directory not found"
    echo "Creating directory and copying config..."
    
    mkdir -p /etc/pyslirp
    chmod 755 /etc/pyslirp
    
    if [[ -f config.yaml ]]; then
        cp config.yaml /etc/pyslirp/
        # Detect group
        PYSLIRP_GROUP=$(groups pyslirp 2>/dev/null | cut -d: -f2 | tr ' ' '\n' | grep -E 'dialout|uucp|serial|tty' | head -1)
        if [[ -z "$PYSLIRP_GROUP" ]]; then
            PYSLIRP_GROUP="dialout"
        fi
        chown root:$PYSLIRP_GROUP /etc/pyslirp/config.yaml
        chmod 640 /etc/pyslirp/config.yaml
        echo "Directory created and config installed"
    else
        echo "Error: No config.yaml found in current directory"
        exit 1
    fi
fi

# Verify pyslirp user exists and is in the right group
if id pyslirp &>/dev/null; then
    echo ""
    echo "PyLiRP user groups:"
    groups pyslirp
else
    echo "Warning: pyslirp user does not exist"
fi

# Check log directory
if [[ -d /var/log/pyslirp ]]; then
    echo ""
    echo "Log directory permissions:"
    ls -ld /var/log/pyslirp
else
    echo "Creating log directory..."
    mkdir -p /var/log/pyslirp
    chown pyslirp:$PYSLIRP_GROUP /var/log/pyslirp
    chmod 755 /var/log/pyslirp
fi

echo ""
echo "Permission fix complete!"
echo ""
echo "You can now:"
echo "1. Restart the service: systemctl restart pyslirp"
echo "2. Check status: systemctl status pyslirp"
echo "3. View logs: journalctl -u pyslirp -f"