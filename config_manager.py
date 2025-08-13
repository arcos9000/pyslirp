#!/usr/bin/env python3
"""
Configuration Management System for PyLiRP
Handles YAML configuration loading, validation, and environment-specific overrides
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, field
from copy import deepcopy

from safe_logger import get_safe_logger

logger = get_safe_logger(__name__)

@dataclass
class SerialConfig:
    """Serial port configuration"""
    port: str = "/dev/ttyUSB0"
    baudrate: int = 115200
    flow_control: str = "hardware"  # none/hardware/software
    timeout: float = 5.0
    write_timeout: float = 2.0

@dataclass
class NetworkConfig:
    """Network configuration"""
    local_ip: str = "10.0.0.1"
    remote_ip: str = "10.0.0.2"
    mtu: int = 1500
    netmask: str = "255.255.255.0"

@dataclass
class PPPConfig:
    """PPP protocol configuration"""
    lcp_echo_interval: int = 30
    lcp_echo_failure_threshold: int = 3
    max_configure_requests: int = 10
    restart_timeout: int = 3
    negotiate_magic: bool = True
    negotiate_mru: bool = True
    negotiate_compression: bool = True
    default_mru: int = 1500
    magic_number: Optional[int] = None

@dataclass
class TCPConfig:
    """TCP stack configuration"""
    initial_window_size: int = 8192
    max_window_size: int = 65535
    mss: int = 1460
    retransmission_timeout_min: int = 200
    retransmission_timeout_max: int = 60000
    max_retransmissions: int = 5
    keepalive_interval: int = 7200
    keepalive_probes: int = 9
    keepalive_probe_interval: int = 75
    time_wait_timeout: int = 120
    congestion_algorithm: str = "reno"
    initial_cwnd: int = 10
    slow_start_threshold: int = 65535
    duplicate_ack_threshold: int = 3

@dataclass
class ServiceConfig:
    """Individual service configuration"""
    host: str = "127.0.0.1"
    port: int = 80
    name: str = "Unknown Service"
    enabled: bool = True
    max_connections: int = 50
    connection_timeout: int = 60

@dataclass
class ProxyConfig:
    """Proxy configuration"""
    type: str = "none"  # none/socks5/http
    host: str = "127.0.0.1"
    port: int = 1080
    username: Optional[str] = None
    password: Optional[str] = None
    connection_timeout: int = 10
    enabled: bool = False

@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    enabled: bool = True
    connections_per_second: int = 10
    burst_size: int = 20
    window_size: int = 60

@dataclass
class ConnectionLimitsConfig:
    """Connection limits configuration"""
    global_max_connections: int = 200
    per_service_max: int = 50
    per_ip_max: int = 20

@dataclass
class SecurityConfig:
    """Security configuration"""
    allowed_ports: List[int] = field(default_factory=lambda: [22, 80, 443])
    blocked_ips: List[str] = field(default_factory=list)
    rate_limiting: RateLimitConfig = field(default_factory=RateLimitConfig)
    connection_limits: ConnectionLimitsConfig = field(default_factory=ConnectionLimitsConfig)
    log_security_events: bool = True
    log_rejected_connections: bool = True
    log_rate_limit_violations: bool = True

@dataclass
class FileLoggingConfig:
    """File logging configuration"""
    enabled: bool = True
    path: str = "/var/log/pyslirp.log"
    max_size: str = "10MB"
    rotate_count: int = 5

@dataclass
class ConsoleLoggingConfig:
    """Console logging configuration"""
    enabled: bool = True
    color: bool = True

@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    file: FileLoggingConfig = field(default_factory=FileLoggingConfig)
    console: ConsoleLoggingConfig = field(default_factory=ConsoleLoggingConfig)
    components: Dict[str, str] = field(default_factory=lambda: {
        'ppp': 'INFO',
        'tcp': 'INFO', 
        'serial': 'INFO',
        'proxy': 'INFO',
        'security': 'INFO',
        'metrics': 'INFO'
    })

@dataclass
class HealthCheckConfig:
    """Health check configuration"""
    enabled: bool = True
    port: int = 9091
    path: str = "/health"

@dataclass  
class PacketCaptureConfig:
    """Packet capture configuration"""
    enabled: bool = False
    pcap_file: str = "/var/log/pyslirp/pyslirp.pcap"
    max_file_size: str = "100MB"
    rotate_files: bool = True

@dataclass
class PerformanceConfig:
    """Performance monitoring configuration"""
    track_connection_stats: bool = True
    track_bandwidth: bool = True
    track_latency: bool = True
    stats_interval: int = 30

@dataclass
class MonitoringConfig:
    """Monitoring configuration"""
    enable_metrics: bool = True
    metrics_port: int = 9090
    metrics_path: str = "/metrics"
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    packet_capture: PacketCaptureConfig = field(default_factory=PacketCaptureConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)

@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    enabled: bool = True
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3

@dataclass
class ErrorRecoveryConfig:
    """Error recovery configuration"""
    auto_reconnect_serial: bool = True
    serial_reconnect_delay: int = 5
    max_serial_reconnect_attempts: int = 10
    service_retry_delay: int = 1
    max_service_retry_attempts: int = 3
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    ppp_negotiation_timeout: int = 30
    tcp_connection_cleanup_interval: int = 60
    orphaned_connection_timeout: int = 300

@dataclass
class MockServicesConfig:
    """Mock services configuration for testing"""
    enabled: bool = False
    echo_port: int = 7777
    discard_port: int = 7778

@dataclass
class DevelopmentConfig:
    """Development and testing configuration"""
    debug_packets: bool = False
    simulate_packet_loss: bool = False
    packet_loss_rate: float = 0.0
    simulate_latency: bool = False
    artificial_latency_ms: int = 0
    mock_services: MockServicesConfig = field(default_factory=MockServicesConfig)

@dataclass
class Config:
    """Main configuration class"""
    serial: SerialConfig = field(default_factory=SerialConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    ppp: PPPConfig = field(default_factory=PPPConfig)
    tcp: TCPConfig = field(default_factory=TCPConfig)
    services: Dict[int, ServiceConfig] = field(default_factory=dict)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    error_recovery: ErrorRecoveryConfig = field(default_factory=ErrorRecoveryConfig)
    development: DevelopmentConfig = field(default_factory=DevelopmentConfig)
    port_forwards: Dict[int, int] = field(default_factory=dict)  # For client mode: local->remote
    mode: str = "host"  # Operation mode: 'host' or 'client'

class ConfigurationError(Exception):
    """Configuration-related error"""
    pass

class ConfigManager:
    """Configuration manager with validation and environment support"""
    
    def __init__(self):
        self.config: Optional[Config] = None
        self._config_file: Optional[str] = None
        
    def load_config(self, config_file: Optional[str] = None, 
                   environment: Optional[str] = None,
                   mode: Optional[str] = None) -> Config:
        """
        Load configuration from file with environment-specific overrides
        
        Args:
            config_file: Path to main config file (default: config.yaml)
            environment: Environment name for overrides (dev/prod/test)
            mode: Operation mode ('host' or 'client')
            
        Returns:
            Loaded and validated configuration
        """
        # Determine config file path
        if config_file is None:
            config_file = self._find_config_file()
        
        self._config_file = config_file
        
        # Load main configuration
        main_config = self._load_yaml_file(config_file)
        
        # Handle mode selection (host/client)
        if mode and mode in main_config:
            logger.info(f"Using {mode} mode configuration")
            mode_config = main_config[mode]
            # Also include common settings if present
            if 'common' in main_config:
                mode_config = self._merge_configs(main_config['common'], mode_config)
            main_config = mode_config
        elif mode:
            logger.warning(f"Mode '{mode}' not found in config, using full config")
        
        # Load environment-specific overrides
        if environment:
            env_config = self._load_environment_config(config_file, environment)
            if env_config:
                main_config = self._merge_configs(main_config, env_config)
        
        # Apply environment variable overrides
        main_config = self._apply_env_overrides(main_config)
        
        # Create and validate configuration objects
        self.config = self._create_config_objects(main_config)
        
        # Validate configuration
        self._validate_config(self.config)
        
        logger.info(f"Configuration loaded from {config_file}")
        if environment:
            logger.info(f"Applied environment overrides for: {environment}")
            
        return self.config
    
    def _find_config_file(self) -> str:
        """Find configuration file in standard locations"""
        search_paths = [
            "config.yaml",
            "pyslirp.yaml",
            "/etc/pyslirp/config.yaml",
            "/usr/local/etc/pyslirp/config.yaml",
            os.path.expanduser("~/.config/pyslirp/config.yaml"),
            os.path.join(os.path.dirname(__file__), "config.yaml")
        ]
        
        for path in search_paths:
            if os.path.isfile(path):
                return path
                
        raise ConfigurationError(
            f"Configuration file not found. Searched: {search_paths}"
        )
    
    def _load_yaml_file(self, file_path: str) -> Dict[str, Any]:
        """Load YAML configuration file"""
        try:
            with open(file_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            raise ConfigurationError(f"Configuration file not found: {file_path}")
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in {file_path}: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error loading {file_path}: {e}")
    
    def _load_environment_config(self, base_config_path: str, 
                                environment: str) -> Optional[Dict[str, Any]]:
        """Load environment-specific configuration overrides"""
        base_dir = os.path.dirname(base_config_path)
        base_name = os.path.splitext(os.path.basename(base_config_path))[0]
        
        env_file = os.path.join(base_dir, f"{base_name}.{environment}.yaml")
        
        if os.path.isfile(env_file):
            logger.info(f"Loading environment config: {env_file}")
            return self._load_yaml_file(env_file)
        
        return None
    
    def _merge_configs(self, base: Dict[str, Any], 
                      override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge configuration dictionaries"""
        result = deepcopy(base)
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
                
        return result
    
    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides using PYSLIRP_ prefix"""
        result = deepcopy(config)
        
        # Define environment variable mappings
        env_mappings = {
            'PYSLIRP_SERIAL_PORT': ['serial', 'port'],
            'PYSLIRP_SERIAL_BAUDRATE': ['serial', 'baudrate'],
            'PYSLIRP_LOCAL_IP': ['network', 'local_ip'],
            'PYSLIRP_REMOTE_IP': ['network', 'remote_ip'],
            'PYSLIRP_LOG_LEVEL': ['logging', 'level'],
            'PYSLIRP_LOG_FILE': ['logging', 'file', 'path'],
            'PYSLIRP_SOCKS_HOST': ['proxy', 'host'],
            'PYSLIRP_SOCKS_PORT': ['proxy', 'port'],
            'PYSLIRP_METRICS_PORT': ['monitoring', 'metrics_port'],
        }
        
        for env_var, config_path in env_mappings.items():
            env_value = os.environ.get(env_var)
            if env_value is not None:
                # Navigate to the nested dictionary
                current = result
                for key in config_path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                
                # Convert value to appropriate type
                final_key = config_path[-1]
                if final_key in ['baudrate', 'port', 'metrics_port']:
                    current[final_key] = int(env_value)
                else:
                    current[final_key] = env_value
                    
                logger.info(f"Applied environment override: {env_var}={env_value}")
        
        return result
    
    def _create_config_objects(self, config_dict: Dict[str, Any]) -> Config:
        """Create configuration objects from dictionary"""
        try:
            # Create service configurations
            services = {}
            if 'services' in config_dict:
                for port, service_config in config_dict['services'].items():
                    services[int(port)] = ServiceConfig(**service_config)
            
            # Create main config object
            config_kwargs = {}
            
            for section_name, section_class in [
                ('serial', SerialConfig),
                ('network', NetworkConfig),  
                ('ppp', PPPConfig),
                ('tcp', TCPConfig),
                ('proxy', ProxyConfig),
                ('security', SecurityConfig),
                ('logging', LoggingConfig),
                ('monitoring', MonitoringConfig),
                ('error_recovery', ErrorRecoveryConfig),
                ('development', DevelopmentConfig),
            ]:
                if section_name in config_dict:
                    config_kwargs[section_name] = self._create_nested_config(
                        config_dict[section_name], section_class
                    )
            
            config_kwargs['services'] = services
            
            # Handle port_forwards (for client mode)
            if 'port_forwards' in config_dict:
                # Convert string keys to integers
                port_forwards = {}
                for local_port, remote_port in config_dict['port_forwards'].items():
                    port_forwards[int(local_port)] = int(remote_port)
                config_kwargs['port_forwards'] = port_forwards
            
            return Config(**config_kwargs)
            
        except Exception as e:
            raise ConfigurationError(f"Error creating configuration objects: {e}")
    
    def _create_nested_config(self, config_dict: Dict[str, Any], 
                            config_class: type) -> Any:
        """Create nested configuration objects recursively"""
        # Handle nested dataclasses
        annotations = getattr(config_class, '__annotations__', {})
        kwargs = {}
        
        for field_name, field_type in annotations.items():
            if field_name in config_dict:
                value = config_dict[field_name]
                
                # Check if it's a nested dataclass
                if hasattr(field_type, '__annotations__'):
                    kwargs[field_name] = self._create_nested_config(value, field_type)
                else:
                    kwargs[field_name] = value
        
        return config_class(**kwargs)
    
    def _validate_config(self, config: Config):
        """Validate configuration for consistency and correctness"""
        errors = []
        
        # Validate serial port
        if not config.serial.port:
            errors.append("Serial port must be specified")
        
        # Validate IP addresses
        try:
            import ipaddress
            ipaddress.ip_address(config.network.local_ip)
            ipaddress.ip_address(config.network.remote_ip)
        except ValueError as e:
            errors.append(f"Invalid IP address: {e}")
        
        # Validate port ranges
        for port in config.services:
            if not (1 <= port <= 65535):
                errors.append(f"Invalid service port: {port}")
        
        # Validate proxy configuration
        if config.proxy.enabled and config.proxy.type not in ['socks5', 'http']:
            errors.append(f"Invalid proxy type: {config.proxy.type}")
        
        # Validate logging level
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if config.logging.level not in valid_levels:
            errors.append(f"Invalid log level: {config.logging.level}")
        
        # Validate TCP configuration
        if config.tcp.initial_window_size <= 0:
            errors.append("TCP initial window size must be positive")
        
        if config.tcp.mss <= 0:
            errors.append("TCP MSS must be positive")
        
        if errors:
            raise ConfigurationError("Configuration validation failed:\n" + 
                                   "\n".join(f"  - {error}" for error in errors))
    
    def get_config(self) -> Config:
        """Get current configuration (must be loaded first)"""
        if self.config is None:
            raise ConfigurationError("Configuration not loaded. Call load_config() first.")
        return self.config
    
    def reload_config(self):
        """Reload configuration from file"""
        if self._config_file is None:
            raise ConfigurationError("No configuration file to reload")
        self.load_config(self._config_file)
    
    def get_service_config(self, port: int) -> Optional[ServiceConfig]:
        """Get configuration for a specific service port"""
        if self.config is None:
            return None
        return self.config.services.get(port)
    
    def is_port_allowed(self, port: int) -> bool:
        """Check if a port is allowed by security configuration"""
        if self.config is None:
            return False
        return port in self.config.security.allowed_ports
    
    def is_ip_blocked(self, ip: str) -> bool:
        """Check if an IP address is blocked"""
        if self.config is None:
            return False
        return ip in self.config.security.blocked_ips

# Global configuration manager instance
config_manager = ConfigManager()

def load_config(config_file: Optional[str] = None, 
               environment: Optional[str] = None) -> Config:
    """Load configuration (convenience function)"""
    return config_manager.load_config(config_file, environment)

def get_config() -> Config:
    """Get current configuration (convenience function)"""
    return config_manager.get_config()