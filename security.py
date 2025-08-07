#!/usr/bin/env python3
"""
Security Manager and Access Control for PyLiRP
Provides comprehensive security features including rate limiting, access control,
and security auditing for the userspace SLiRP implementation
"""

import asyncio
import time
import hashlib
import hmac
import json
import ipaddress
from collections import defaultdict, deque
from typing import Dict, Set, Optional, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum, auto
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SecurityEventType(Enum):
    """Types of security events"""
    CONNECTION_ALLOWED = auto()
    CONNECTION_DENIED = auto()
    RATE_LIMIT_EXCEEDED = auto()
    SUSPICIOUS_ACTIVITY = auto()
    AUTHENTICATION_FAILED = auto()
    PROTOCOL_VIOLATION = auto()
    BRUTE_FORCE_DETECTED = auto()
    IP_BLOCKED = auto()
    SERVICE_UNAUTHORIZED = auto()

class ThreatLevel(Enum):
    """Threat levels for security events"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityEvent:
    """Represents a security event"""
    event_type: SecurityEventType
    threat_level: ThreatLevel
    source_ip: str
    destination_port: int
    timestamp: float
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization"""
        return {
            'event_type': self.event_type.name,
            'threat_level': self.threat_level.value,
            'source_ip': self.source_ip,
            'destination_port': self.destination_port,
            'timestamp': self.timestamp,
            'timestamp_iso': datetime.fromtimestamp(self.timestamp).isoformat(),
            'description': self.description,
            'metadata': self.metadata
        }

@dataclass
class ConnectionAttempt:
    """Tracks connection attempt for rate limiting and analysis"""
    timestamp: float
    source_ip: str
    destination_port: int
    success: bool
    
class RateLimiter:
    """Token bucket rate limiter with burst support"""
    
    def __init__(self, rate: float, burst_size: int, window_size: int = 60):
        self.rate = rate  # requests per second
        self.burst_size = burst_size
        self.window_size = window_size
        
        # Token bucket per IP
        self._buckets: Dict[str, Tuple[float, float]] = {}  # (tokens, last_update)
        
        # Connection tracking
        self._connection_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup()
    
    def allow(self, source_ip: str) -> bool:
        """Check if request is allowed under rate limit"""
        current_time = time.time()
        
        # Get or create bucket
        if source_ip not in self._buckets:
            self._buckets[source_ip] = (self.burst_size, current_time)
        
        tokens, last_update = self._buckets[source_ip]
        
        # Add tokens based on elapsed time
        time_elapsed = current_time - last_update
        tokens = min(self.burst_size, tokens + (time_elapsed * self.rate))
        
        if tokens >= 1.0:
            # Allow request and consume token
            tokens -= 1.0
            self._buckets[source_ip] = (tokens, current_time)
            
            # Record successful attempt
            self._connection_history[source_ip].append(
                ConnectionAttempt(current_time, source_ip, 0, True)
            )
            return True
        else:
            # Rate limit exceeded
            self._buckets[source_ip] = (tokens, current_time)
            
            # Record failed attempt
            self._connection_history[source_ip].append(
                ConnectionAttempt(current_time, source_ip, 0, False)
            )
            return False
    
    def get_current_rate(self, source_ip: str) -> float:
        """Get current connection rate for IP"""
        current_time = time.time()
        cutoff_time = current_time - self.window_size
        
        if source_ip not in self._connection_history:
            return 0.0
        
        recent_attempts = [
            attempt for attempt in self._connection_history[source_ip]
            if attempt.timestamp > cutoff_time
        ]
        
        return len(recent_attempts) / self.window_size
    
    def is_suspicious(self, source_ip: str) -> bool:
        """Check if IP shows suspicious patterns"""
        if source_ip not in self._connection_history:
            return False
        
        current_time = time.time()
        recent_attempts = [
            attempt for attempt in self._connection_history[source_ip]
            if attempt.timestamp > (current_time - 300)  # Last 5 minutes
        ]
        
        if len(recent_attempts) < 10:
            return False
        
        # Check for high failure rate
        failures = sum(1 for attempt in recent_attempts if not attempt.success)
        failure_rate = failures / len(recent_attempts)
        
        return failure_rate > 0.8  # More than 80% failures
    
    def _start_cleanup(self):
        """Start cleanup task for old buckets"""
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(300)  # Cleanup every 5 minutes
                    current_time = time.time()
                    
                    # Remove old buckets (inactive for more than 1 hour)
                    old_ips = [
                        ip for ip, (_, last_update) in self._buckets.items()
                        if current_time - last_update > 3600
                    ]
                    
                    for ip in old_ips:
                        del self._buckets[ip]
                        if ip in self._connection_history:
                            del self._connection_history[ip]
                    
                    if old_ips:
                        logger.debug(f"Cleaned up {len(old_ips)} old rate limit buckets")
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Rate limiter cleanup error: {e}")
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
    
    async def shutdown(self):
        """Shutdown the rate limiter"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

class AccessControlList:
    """Access control list for IP addresses and ports"""
    
    def __init__(self):
        # IP-based access control
        self._allowed_networks: List[ipaddress.IPv4Network] = []
        self._blocked_networks: List[ipaddress.IPv4Network] = []
        self._blocked_ips: Set[str] = set()
        
        # Port-based access control
        self._allowed_ports: Set[int] = set()
        self._blocked_ports: Set[int] = set()
        
        # Service-specific rules
        self._service_rules: Dict[int, Dict[str, Any]] = {}
        
        # Temporary blocks (IP -> expiry timestamp)
        self._temp_blocks: Dict[str, float] = {}
    
    def add_allowed_network(self, network: str):
        """Add allowed network (CIDR notation)"""
        try:
            net = ipaddress.IPv4Network(network, strict=False)
            self._allowed_networks.append(net)
            logger.info(f"Added allowed network: {network}")
        except ValueError as e:
            logger.error(f"Invalid network format: {network}: {e}")
    
    def add_blocked_network(self, network: str):
        """Add blocked network (CIDR notation)"""
        try:
            net = ipaddress.IPv4Network(network, strict=False)
            self._blocked_networks.append(net)
            logger.info(f"Added blocked network: {network}")
        except ValueError as e:
            logger.error(f"Invalid network format: {network}: {e}")
    
    def block_ip(self, ip: str, duration: Optional[int] = None):
        """Block IP address permanently or temporarily"""
        if duration:
            # Temporary block
            expiry = time.time() + duration
            self._temp_blocks[ip] = expiry
            logger.info(f"Temporarily blocked IP {ip} for {duration} seconds")
        else:
            # Permanent block
            self._blocked_ips.add(ip)
            logger.info(f"Permanently blocked IP: {ip}")
    
    def unblock_ip(self, ip: str):
        """Unblock IP address"""
        self._blocked_ips.discard(ip)
        self._temp_blocks.pop(ip, None)
        logger.info(f"Unblocked IP: {ip}")
    
    def is_ip_allowed(self, ip: str) -> bool:
        """Check if IP address is allowed"""
        try:
            ip_addr = ipaddress.IPv4Address(ip)
            
            # Check temporary blocks first
            if ip in self._temp_blocks:
                if time.time() < self._temp_blocks[ip]:
                    return False  # Still blocked
                else:
                    # Block expired, remove it
                    del self._temp_blocks[ip]
            
            # Check permanent blocks
            if ip in self._blocked_ips:
                return False
            
            # Check blocked networks
            for network in self._blocked_networks:
                if ip_addr in network:
                    return False
            
            # Check allowed networks (if any are defined)
            if self._allowed_networks:
                for network in self._allowed_networks:
                    if ip_addr in network:
                        return True
                return False  # Not in any allowed network
            
            # Default allow if no specific rules
            return True
            
        except ValueError:
            # Invalid IP format
            return False
    
    def is_port_allowed(self, port: int) -> bool:
        """Check if port is allowed"""
        # Check explicit blocks first
        if port in self._blocked_ports:
            return False
        
        # Check allowed ports (if any are defined)
        if self._allowed_ports:
            return port in self._allowed_ports
        
        # Default allow if no specific port rules
        return True
    
    def add_service_rule(self, port: int, max_connections: int = 50,
                        allowed_ips: Optional[List[str]] = None):
        """Add service-specific access rule"""
        rule = {
            'max_connections': max_connections,
            'allowed_ips': set(allowed_ips or []),
            'current_connections': 0
        }
        self._service_rules[port] = rule
        logger.info(f"Added service rule for port {port}: max_conn={max_connections}")
    
    def check_service_access(self, ip: str, port: int) -> bool:
        """Check if IP can access specific service"""
        if port not in self._service_rules:
            return True  # No specific rules
        
        rule = self._service_rules[port]
        
        # Check IP-specific restrictions
        if rule['allowed_ips'] and ip not in rule['allowed_ips']:
            return False
        
        # Check connection limit
        if rule['current_connections'] >= rule['max_connections']:
            return False
        
        return True
    
    def increment_service_connections(self, port: int):
        """Increment connection count for service"""
        if port in self._service_rules:
            self._service_rules[port]['current_connections'] += 1
    
    def decrement_service_connections(self, port: int):
        """Decrement connection count for service"""
        if port in self._service_rules:
            rule = self._service_rules[port]
            rule['current_connections'] = max(0, rule['current_connections'] - 1)

class BruteForceDetector:
    """Detects brute force attacks and suspicious patterns"""
    
    def __init__(self, failure_threshold: int = 5, 
                 time_window: int = 300, block_duration: int = 3600):
        self.failure_threshold = failure_threshold
        self.time_window = time_window  # 5 minutes
        self.block_duration = block_duration  # 1 hour
        
        # Track failed attempts per IP
        self._failed_attempts: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )
        
        # Track detected attacks
        self._detected_attacks: Dict[str, float] = {}  # IP -> detection time
    
    def record_failure(self, ip: str, port: int) -> bool:
        """
        Record failed connection attempt
        
        Returns:
            True if brute force detected, False otherwise
        """
        current_time = time.time()
        
        # Add failed attempt
        self._failed_attempts[ip].append((current_time, port))
        
        # Check for brute force pattern
        recent_failures = [
            (timestamp, port) for timestamp, port in self._failed_attempts[ip]
            if current_time - timestamp < self.time_window
        ]
        
        if len(recent_failures) >= self.failure_threshold:
            # Check if this is a new attack or ongoing
            if ip not in self._detected_attacks:
                self._detected_attacks[ip] = current_time
                logger.warning(
                    f"Brute force attack detected from {ip}: "
                    f"{len(recent_failures)} failures in {self.time_window}s"
                )
                return True
        
        return False
    
    def is_under_attack(self, ip: str) -> bool:
        """Check if IP is currently launching an attack"""
        if ip not in self._detected_attacks:
            return False
        
        attack_time = self._detected_attacks[ip]
        
        # Check if attack is still active (within block duration)
        if time.time() - attack_time > self.block_duration:
            del self._detected_attacks[ip]
            return False
        
        return True
    
    def get_attack_info(self, ip: str) -> Optional[Dict[str, Any]]:
        """Get information about detected attack"""
        if not self.is_under_attack(ip):
            return None
        
        attack_time = self._detected_attacks[ip]
        recent_attempts = [
            (timestamp, port) for timestamp, port in self._failed_attempts[ip]
            if timestamp > attack_time - self.time_window
        ]
        
        # Group attempts by port
        port_attempts = defaultdict(int)
        for _, port in recent_attempts:
            port_attempts[port] += 1
        
        return {
            'attack_start': attack_time,
            'total_attempts': len(recent_attempts),
            'target_ports': dict(port_attempts),
            'duration': time.time() - attack_time
        }

class SecurityAuditor:
    """Security audit logger and analyzer"""
    
    def __init__(self, log_file: Optional[str] = None):
        self.log_file = log_file
        self._events: deque = deque(maxlen=10000)  # Keep last 10k events
        self._event_counts: Dict[SecurityEventType, int] = defaultdict(int)
        
        # Setup file logging if specified
        self._file_handler = None
        if log_file:
            self._setup_file_logging()
    
    def _setup_file_logging(self):
        """Setup file logging for security events"""
        try:
            import logging.handlers
            
            # Create rotating file handler
            self._file_handler = logging.handlers.RotatingFileHandler(
                self.log_file,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            
            # JSON formatter for structured logs
            formatter = logging.Formatter(
                '%(asctime)s - SECURITY - %(message)s'
            )
            self._file_handler.setFormatter(formatter)
            
            # Add to security logger
            security_logger = logging.getLogger('security')
            security_logger.addHandler(self._file_handler)
            security_logger.setLevel(logging.INFO)
            
        except Exception as e:
            logger.error(f"Failed to setup security audit logging: {e}")
    
    def log_event(self, event: SecurityEvent):
        """Log security event"""
        self._events.append(event)
        self._event_counts[event.event_type] += 1
        
        # Log to file if configured
        if self._file_handler:
            security_logger = logging.getLogger('security')
            security_logger.info(json.dumps(event.to_dict()))
        
        # Log to main logger based on threat level
        if event.threat_level == ThreatLevel.CRITICAL:
            logger.critical(f"SECURITY: {event.description}")
        elif event.threat_level == ThreatLevel.HIGH:
            logger.error(f"SECURITY: {event.description}")
        elif event.threat_level == ThreatLevel.MEDIUM:
            logger.warning(f"SECURITY: {event.description}")
        else:
            logger.info(f"SECURITY: {event.description}")
    
    def get_security_summary(self, time_range: int = 3600) -> Dict[str, Any]:
        """Get security summary for specified time range (seconds)"""
        current_time = time.time()
        cutoff_time = current_time - time_range
        
        recent_events = [
            event for event in self._events
            if event.timestamp > cutoff_time
        ]
        
        # Count events by type
        event_counts = defaultdict(int)
        threat_counts = defaultdict(int)
        ip_counts = defaultdict(int)
        port_counts = defaultdict(int)
        
        for event in recent_events:
            event_counts[event.event_type.name] += 1
            threat_counts[event.threat_level.value] += 1
            ip_counts[event.source_ip] += 1
            port_counts[event.destination_port] += 1
        
        return {
            'time_range_hours': time_range / 3600,
            'total_events': len(recent_events),
            'event_types': dict(event_counts),
            'threat_levels': dict(threat_counts),
            'top_source_ips': dict(sorted(ip_counts.items(), 
                                        key=lambda x: x[1], reverse=True)[:10]),
            'top_target_ports': dict(sorted(port_counts.items(),
                                          key=lambda x: x[1], reverse=True)[:10])
        }
    
    def generate_security_report(self) -> str:
        """Generate human-readable security report"""
        summary = self.get_security_summary()
        
        report = f"""
Security Report - Last {summary['time_range_hours']:.1f} hours
{'='*50}

Total Security Events: {summary['total_events']}

Event Types:
{self._format_dict(summary['event_types'])}

Threat Levels:
{self._format_dict(summary['threat_levels'])}

Top Source IPs:
{self._format_dict(summary['top_source_ips'])}

Top Target Ports:
{self._format_dict(summary['top_target_ports'])}
"""
        return report
    
    def _format_dict(self, d: Dict[str, int], indent: int = 4) -> str:
        """Format dictionary for report display"""
        if not d:
            return " " * indent + "None"
        
        lines = []
        for key, value in d.items():
            lines.append(" " * indent + f"{key}: {value}")
        return "\n".join(lines)

class SecurityManager:
    """Main security manager coordinating all security components"""
    
    def __init__(self, config: Dict[str, Any]):
        # Initialize components
        self.rate_limiter = RateLimiter(
            rate=config.get('rate_limiting', {}).get('connections_per_second', 10),
            burst_size=config.get('rate_limiting', {}).get('burst_size', 20),
            window_size=config.get('rate_limiting', {}).get('window_size', 60)
        )
        
        self.acl = AccessControlList()
        self.brute_force_detector = BruteForceDetector(
            failure_threshold=config.get('brute_force', {}).get('threshold', 5),
            time_window=config.get('brute_force', {}).get('window', 300),
            block_duration=config.get('brute_force', {}).get('block_duration', 3600)
        )
        
        self.auditor = SecurityAuditor(
            log_file=config.get('audit_log_file')
        )
        
        # Configuration
        self._config = config
        self._enabled = config.get('enabled', True)
        
        # Initialize ACL from config
        self._initialize_acl()
        
        logger.info("Security manager initialized")
    
    def _initialize_acl(self):
        """Initialize ACL from configuration"""
        # Add allowed/blocked ports
        allowed_ports = self._config.get('allowed_ports', [])
        for port in allowed_ports:
            self.acl._allowed_ports.add(port)
        
        blocked_ips = self._config.get('blocked_ips', [])
        for ip in blocked_ips:
            self.acl.block_ip(ip)
        
        # Add service rules
        connection_limits = self._config.get('connection_limits', {})
        per_service_max = connection_limits.get('per_service_max', 50)
        
        for port in allowed_ports:
            self.acl.add_service_rule(port, max_connections=per_service_max)
    
    async def validate_connection(self, src_ip: str, dst_port: int) -> Tuple[bool, str]:
        """
        Validate incoming connection request
        
        Returns:
            Tuple of (allowed, reason)
        """
        if not self._enabled:
            return True, "Security disabled"
        
        # Check if IP is under brute force attack
        if self.brute_force_detector.is_under_attack(src_ip):
            event = SecurityEvent(
                event_type=SecurityEventType.CONNECTION_DENIED,
                threat_level=ThreatLevel.HIGH,
                source_ip=src_ip,
                destination_port=dst_port,
                timestamp=time.time(),
                description=f"Connection denied: IP {src_ip} is under attack detection",
                metadata={'reason': 'brute_force_detected'}
            )
            self.auditor.log_event(event)
            return False, "IP blocked due to brute force detection"
        
        # Check IP access control
        if not self.acl.is_ip_allowed(src_ip):
            event = SecurityEvent(
                event_type=SecurityEventType.CONNECTION_DENIED,
                threat_level=ThreatLevel.MEDIUM,
                source_ip=src_ip,
                destination_port=dst_port,
                timestamp=time.time(),
                description=f"Connection denied: IP {src_ip} is blocked",
                metadata={'reason': 'ip_blocked'}
            )
            self.auditor.log_event(event)
            return False, "IP address blocked"
        
        # Check port access control
        if not self.acl.is_port_allowed(dst_port):
            event = SecurityEvent(
                event_type=SecurityEventType.CONNECTION_DENIED,
                threat_level=ThreatLevel.LOW,
                source_ip=src_ip,
                destination_port=dst_port,
                timestamp=time.time(),
                description=f"Connection denied: Port {dst_port} not allowed",
                metadata={'reason': 'port_not_allowed'}
            )
            self.auditor.log_event(event)
            return False, "Port not allowed"
        
        # Check service-specific access
        if not self.acl.check_service_access(src_ip, dst_port):
            event = SecurityEvent(
                event_type=SecurityEventType.CONNECTION_DENIED,
                threat_level=ThreatLevel.MEDIUM,
                source_ip=src_ip,
                destination_port=dst_port,
                timestamp=time.time(),
                description=f"Connection denied: Service access restricted for {src_ip}:{dst_port}",
                metadata={'reason': 'service_restricted'}
            )
            self.auditor.log_event(event)
            return False, "Service access restricted"
        
        # Check rate limiting
        if not self.rate_limiter.allow(src_ip):
            event = SecurityEvent(
                event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
                threat_level=ThreatLevel.MEDIUM,
                source_ip=src_ip,
                destination_port=dst_port,
                timestamp=time.time(),
                description=f"Rate limit exceeded for {src_ip}",
                metadata={
                    'reason': 'rate_limit',
                    'current_rate': self.rate_limiter.get_current_rate(src_ip)
                }
            )
            self.auditor.log_event(event)
            return False, "Rate limit exceeded"
        
        # All checks passed
        event = SecurityEvent(
            event_type=SecurityEventType.CONNECTION_ALLOWED,
            threat_level=ThreatLevel.LOW,
            source_ip=src_ip,
            destination_port=dst_port,
            timestamp=time.time(),
            description=f"Connection allowed: {src_ip}:{dst_port}",
            metadata={'reason': 'all_checks_passed'}
        )
        self.auditor.log_event(event)
        
        # Increment service connection count
        self.acl.increment_service_connections(dst_port)
        
        return True, "Connection allowed"
    
    async def handle_connection_failure(self, src_ip: str, dst_port: int, 
                                      reason: str = "unknown"):
        """Handle failed connection attempt"""
        # Record brute force attempt
        if self.brute_force_detector.record_failure(src_ip, dst_port):
            # Brute force detected, block IP temporarily
            self.acl.block_ip(src_ip, duration=3600)  # 1 hour block
            
            event = SecurityEvent(
                event_type=SecurityEventType.BRUTE_FORCE_DETECTED,
                threat_level=ThreatLevel.HIGH,
                source_ip=src_ip,
                destination_port=dst_port,
                timestamp=time.time(),
                description=f"Brute force attack detected and IP blocked: {src_ip}",
                metadata={
                    'reason': reason,
                    'attack_info': self.brute_force_detector.get_attack_info(src_ip)
                }
            )
            self.auditor.log_event(event)
    
    async def handle_connection_close(self, src_ip: str, dst_port: int):
        """Handle connection close"""
        # Decrement service connection count
        self.acl.decrement_service_connections(dst_port)
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get current security status"""
        return {
            'enabled': self._enabled,
            'rate_limiter': {
                'active_buckets': len(self.rate_limiter._buckets),
                'suspicious_ips': [
                    ip for ip in self.rate_limiter._buckets
                    if self.rate_limiter.is_suspicious(ip)
                ]
            },
            'access_control': {
                'allowed_ports': len(self.acl._allowed_ports),
                'blocked_ips': len(self.acl._blocked_ips),
                'temp_blocks': len(self.acl._temp_blocks),
                'service_rules': len(self.acl._service_rules)
            },
            'brute_force': {
                'detected_attacks': len(self.brute_force_detector._detected_attacks),
                'monitored_ips': len(self.brute_force_detector._failed_attempts)
            },
            'audit': {
                'total_events': len(self.auditor._events),
                'event_types': dict(self.auditor._event_counts)
            }
        }
    
    async def shutdown(self):
        """Shutdown security manager"""
        logger.info("Shutting down security manager")
        await self.rate_limiter.shutdown()