# Python SLiRP Implementation Project

## Project Overview
Creating a modern Python replacement for SLiRP (Serial Line IP) that operates **completely in userspace** without requiring root privileges or interacting with the OS networking stack. The goal is to provide PPP over serial connectivity to access local services (primarily SSH) without exposing any networking configuration to the host OS.

## Critical Design Requirement: Complete Userspace Operation

### How It Stays in Userspace
1. **No OS network interfaces**: The 10.0.0.0/24 IPs exist only within the Python application's memory
2. **No kernel involvement**: Never creates tun/tap interfaces or modifies routing tables
3. **Serial port access only**: Uses standard read()/write() operations on /dev/ttyUSB* (requires only user group membership, typically 'dialout')
4. **Regular socket clients**: Outbound connections use standard unprivileged socket() calls

### IP Address Isolation
- **10.0.0.1** (server) and **10.0.0.2** (client) IPs are **never exposed to the host OS**
- These addresses exist only:
  - In PPP frames over the serial link
  - In Python application memory for packet processing
  - Never in OS routing tables, interfaces, or netstat output
- The host OS has no awareness these IPs exist

### Data Flow Architecture
```
[Remote PPP Client]
    | (10.0.0.2)
    | PPP frames over serial cable
    ↓
[Serial Port: /dev/ttyUSB0]
    |
    | read()/write() - regular file I/O
    ↓
[Python SLiRP Process] (runs as regular user)
    | Parses PPP/IP/TCP in Python memory
    | Maintains TCP state machine in Python
    | Translates to socket operations
    ↓
[Standard Socket Calls]
    | connect("127.0.0.1", 22) - regular outbound connection
    ↓
[Local SSH Server or SOCKS Proxy]
```

## Current Implementation Status

### Completed Components
1. **PPP Frame Handler**: Processes PPP framing/escaping over serial
2. **Minimal TCP/IP Stack**: Userspace implementation with checksums
3. **Service Proxy**: Maps incoming connections to localhost services
4. **SOCKS5 Client**: Optional routing through SOCKS proxy
5. **Async Architecture**: Full asyncio support for performance

### Working Features
- PPP frame processing with proper escape sequences
- TCP three-way handshake
- Basic data forwarding
- Service port mapping (SSH, HTTP, etc.)
- Connection state tracking

## Production Enhancement Proposals

### 1. Robust PPP Negotiation
```python
class PPPNegotiator:
    """Full PPP LCP/IPCP negotiation implementation"""
    
    async def negotiate_lcp(self, serial_writer):
        """
        Link Control Protocol negotiation:
        - Magic number negotiation
        - MRU (Maximum Receive Unit) configuration
        - Authentication protocol selection
        - Compression options
        """
        pass
    
    async def negotiate_ipcp(self, serial_writer):
        """
        IP Control Protocol negotiation:
        - IP address assignment (10.0.0.1/10.0.0.2)
        - DNS server configuration (optional)
        - IP compression options
        """
        pass
    
    async def handle_echo_request(self, packet):
        """Respond to LCP echo for keepalive"""
        pass
```

### 2. Complete TCP State Machine
```python
class TCPStateMachine:
    """Full RFC 793 compliant TCP implementation"""
    
    def __init__(self):
        self.state = TCPState.CLOSED
        self.retransmission_queue = []
        self.congestion_window = 1
        self.rtt_estimator = RTTEstimator()
    
    async def handle_segment(self, segment):
        """Process TCP segment according to current state"""
        # Implement full state transition diagram
        # Handle retransmissions
        # Implement congestion control (Reno/Cubic)
        # Process TCP options (MSS, Window Scale, SACK)
        pass
    
    async def handle_timeout(self):
        """Retransmission timeout handling"""
        pass
```

### 3. Configuration Management
```yaml
# config.yaml
serial:
  port: /dev/ttyUSB0
  baudrate: 115200
  flow_control: hardware  # none/hardware/software
  
network:
  local_ip: 10.0.0.1
  remote_ip: 10.0.0.2
  mtu: 1500
  
ppp:
  lcp_echo_interval: 30
  max_configure_requests: 10
  negotiate_magic: true
  
services:
  # Port mapping: PPP client port -> local service
  22: 
    host: 127.0.0.1
    port: 22
    name: SSH
  80:
    host: 127.0.0.1
    port: 8080
    name: HTTP
  443:
    host: 127.0.0.1
    port: 443
    name: HTTPS
    
proxy:
  type: socks5  # none/socks5/http
  host: 127.0.0.1
  port: 1080
  username: null
  password: null
  
logging:
  level: INFO
  file: /var/log/pyslirp.log
  max_size: 10MB
  rotate_count: 5
  
monitoring:
  enable_metrics: true
  metrics_port: 9090  # Prometheus metrics endpoint
  enable_packet_capture: false
  pcap_file: /tmp/pyslirp.pcap
```

### 4. Connection Pool & Performance
```python
class ConnectionPool:
    """Efficient connection management"""
    
    def __init__(self, max_connections=100, idle_timeout=300):
        self.active_connections = {}
        self.connection_cache = LRUCache(max_connections)
        self.idle_timeout = idle_timeout
    
    async def get_or_create_connection(self, service_key):
        """Reuse existing connections when possible"""
        if service_key in self.connection_cache:
            conn = self.connection_cache[service_key]
            if await self.is_connection_alive(conn):
                return conn
        
        return await self.create_new_connection(service_key)
    
    async def cleanup_idle_connections(self):
        """Periodic cleanup of idle connections"""
        pass
```

### 5. Security Enhancements
```python
class SecurityManager:
    """Security and access control"""
    
    def __init__(self, config):
        self.allowed_ports = set(config.get('allowed_ports', []))
        self.rate_limiter = RateLimiter()
        self.connection_limits = config.get('connection_limits', {})
    
    async def validate_connection(self, src_port, dst_port, src_ip):
        """Validate incoming connection request"""
        # Check if port is allowed
        if dst_port not in self.allowed_ports:
            return False
        
        # Rate limiting
        if not self.rate_limiter.allow(src_ip):
            return False
        
        # Connection limits per service
        if self.get_connection_count(dst_port) >= self.connection_limits.get(dst_port, 100):
            return False
        
        return True
    
    async def log_security_event(self, event_type, details):
        """Security audit logging"""
        pass
```

### 6. Monitoring & Observability
```python
class MetricsCollector:
    """Comprehensive metrics collection"""
    
    def __init__(self):
        self.metrics = {
            'bytes_sent': Counter(),
            'bytes_received': Counter(),
            'packets_processed': Counter(),
            'active_connections': Gauge(),
            'connection_errors': Counter(),
            'ppp_errors': Counter(),
            'tcp_retransmissions': Counter(),
            'service_response_time': Histogram(),
        }
    
    async def export_prometheus(self):
        """Export metrics in Prometheus format"""
        pass
    
    async def export_json(self):
        """Export metrics as JSON for custom monitoring"""
        pass
```

### 7. Error Recovery & Resilience
```python
class ErrorRecovery:
    """Robust error handling and recovery"""
    
    async def handle_serial_error(self, error):
        """Serial port error recovery"""
        # Attempt reconnection
        # Buffer data during recovery
        # Notify active connections
        pass
    
    async def handle_service_error(self, service, error):
        """Service connection error handling"""
        # Mark service as unavailable
        # Try alternative endpoints
        # Circuit breaker pattern
        pass
    
    async def handle_protocol_error(self, packet, error):
        """Protocol violation handling"""
        # Log malformed packets
        # Send appropriate error responses
        # Maintain connection stability
        pass
```

### 8. Testing Framework
```python
class TestFramework:
    """Comprehensive testing utilities"""
    
    async def simulate_ppp_client(self):
        """Simulate PPP client for testing"""
        pass
    
    async def inject_packets(self, packets):
        """Inject test packets for protocol testing"""
        pass
    
    async def verify_tcp_compliance(self):
        """RFC 793 compliance testing"""
        pass
    
    async def load_test(self, connections=100, duration=60):
        """Performance and stability testing"""
        pass
```

## Usage Instructions

### Basic Usage
```bash
# Direct connection to local services
python3 pyslirp.py /dev/ttyUSB0

# With configuration file
python3 pyslirp.py -c config.yaml

# With SOCKS proxy
python3 pyslirp.py /dev/ttyUSB0 --socks-host 127.0.0.1 --socks-port 1080

# Debug mode with packet capture
python3 pyslirp.py /dev/ttyUSB0 -d --pcap capture.pcap
```

### Installation
```bash
# Required packages
pip install pyserial pyserial-asyncio pyyaml

# Optional packages for full features
pip install prometheus-client  # For metrics
pip install scapy             # For packet capture
pip install python-socks      # For SOCKS authentication
```

### Running as a Service
```systemd
# /etc/systemd/system/pyslirp.service
[Unit]
Description=Python SLiRP PPP Bridge
After=network.target

[Service]
Type=simple
User=pppuser
Group=dialout
ExecStart=/usr/local/bin/pyslirp -c /etc/pyslirp/config.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Security Considerations

1. **No root required**: Runs entirely as unprivileged user
2. **No kernel modules**: No tun/tap or network stack modifications
3. **Isolated networking**: 10.0.0.0/24 addresses never touch host networking
4. **Service restrictions**: Only configured ports are accessible
5. **Rate limiting**: Prevents DoS attacks over serial
6. **Audit logging**: All connections logged for security review

## Performance Optimization Ideas

1. **PyPy compatibility**: Use PyPy for JIT compilation (~3-5x speedup)
2. **Cython optimization**: Compile critical paths to C
3. **Buffer management**: Implement zero-copy buffers where possible
4. **Packet batching**: Process multiple packets per event loop iteration
5. **Connection caching**: Reuse TCP connections to services

## Alternative Approaches Considered

1. **Using tun/tap**: Rejected - requires root and exposes IPs to OS
2. **iptables/netfilter**: Rejected - requires root and kernel interaction
3. **Full SLIRP port**: Rejected - C code is outdated and hard to maintain
4. **socat/nc chaining**: Rejected - doesn't handle PPP/TCP properly

## Key Technical Challenges Solved

1. **PPP in userspace**: Complete PPP frame handling without kernel PPP
2. **TCP state machine**: Full TCP implementation without OS TCP stack
3. **NAT in userspace**: Address translation without iptables
4. **Service proxying**: Transparent forwarding without REDIRECT rules

## References

- [RFC 1661 - PPP Protocol](https://datatracker.ietf.org/doc/html/rfc1661)
- [RFC 793 - TCP Protocol](https://datatracker.ietf.org/doc/html/rfc793)
- [RFC 1928 - SOCKS5 Protocol](https://datatracker.ietf.org/doc/html/rfc1928)
- [Original SLIRP Documentation](https://gitlab.freedesktop.org/slirp/libslirp)
- [lwIP - Lightweight TCP/IP Stack](https://savannah.nongnu.org/projects/lwip/)
- [gVisor netstack - Userspace TCP/IP](https://github.com/google/gvisor)

## Current Questions/Decisions Needed

1. Should we implement IPv6 support (PPPv6)?
2. Do we need UDP support for any services?
3. Should we add HTTP/HTTPS proxy protocol support?
4. Is ICMP (ping) support needed?
5. Should we implement compression (Van Jacobson, Deflate)?

## Contact & Repository

Project repository: [To be created]
License: MIT (proposed)
Author: [Your details]

---
*This document serves as the complete context for continuing development of the Python SLiRP implementation. All design decisions prioritize userspace operation without requiring root privileges.*