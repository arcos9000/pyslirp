#!/bin/bash
# PyLiRP Deployment Configuration Script

echo "PyLiRP Deployment Configuration"
echo "==============================="
echo ""
echo "Please select your deployment mode:"
echo ""
echo "1. HOST ONLY    - Expose local services to remote clients"
echo "                  (Remote clients connect to YOUR services)"
echo ""
echo "2. CLIENT ONLY  - Connect to remote services"  
echo "                  (YOU connect to remote services on non-conflicting ports)"
echo ""
echo "3. HYBRID       - Both host and client (automatic port offset)"
echo "                  (Bidirectional access with +10000 port offset)"
echo ""

while true; do
    read -p "Select deployment mode [1-3]: " choice
    case $choice in
        1)
            MODE="host"
            CONFIG_FILE="config_host.yaml"
            break
            ;;
        2)
            MODE="client"
            CONFIG_FILE="config_client.yaml"
            break
            ;;
        3)
            MODE="hybrid"
            CONFIG_FILE="config_hybrid.yaml"
            break
            ;;
        *)
            echo "Please enter 1, 2, or 3"
            ;;
    esac
done

echo ""
echo "Selected: $MODE mode"
echo "Using configuration: $CONFIG_FILE"

# Check if config file exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: Configuration file $CONFIG_FILE not found"
    exit 1
fi

# Copy the appropriate config
if [[ -f config.yaml ]]; then
    echo "Backing up existing config.yaml to config.yaml.bak"
    cp config.yaml config.yaml.bak
fi

echo "Installing $MODE configuration..."
cp "$CONFIG_FILE" config.yaml

echo ""
echo "Configuration installed successfully!"
echo ""

# Show deployment-specific information
case $MODE in
    "host")
        echo "HOST MODE Configuration:"
        echo "======================="
        echo "• Exposes YOUR local services to remote PPP clients"
        echo "• Remote clients can access:"
        echo "  - SSH: port 22"
        echo "  - HTTP: port 80"  
        echo "  - HTTPS: port 443"
        echo "  - RDP: port 3389 (if enabled)"
        echo "• Make sure these services are running locally"
        ;;
    "client")
        echo "CLIENT MODE Configuration:"
        echo "========================="
        echo "• Connects to REMOTE services without port conflicts"
        echo "• Access remote services on these local ports:"
        echo "  - Remote SSH: localhost:2222"
        echo "  - Remote HTTP: localhost:8080"
        echo "  - Remote HTTPS: localhost:8443" 
        echo "  - Remote RDP: localhost:13389 (if enabled)"
        echo "• Your local services can still run on standard ports"
        ;;
    "hybrid")
        echo "HYBRID MODE Configuration:"
        echo "========================="
        echo "• Bidirectional access with automatic +10000 port offset"
        echo "• YOUR local services run on standard ports:"
        echo "  - Local SSH: port 22"
        echo "  - Local HTTP: port 80"
        echo "• REMOTE services accessible on offset ports:"
        echo "  - Remote SSH: localhost:10022"
        echo "  - Remote HTTP: localhost:10080"
        echo "  - Remote HTTPS: localhost:10443"
        echo "• No port conflicts - best of both worlds!"
        ;;
esac

echo ""
echo "Next steps:"
echo "1. Edit config.yaml to set your serial port"
echo "2. Enable/disable specific services as needed"
echo "3. Start/restart PyLiRP service"
echo ""
echo "Serial port configuration:"
echo "sed -i 's|port: /dev/ttyUSB0|port: YOUR_SERIAL_PORT|' config.yaml"