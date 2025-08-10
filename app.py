#!/usr/bin/env python3
"""
PyLiRP Application Class
Main application logic separated from entry point
"""

import asyncio
import logging
import platform
from pathlib import Path

from config_manager import ConfigManager
from pySLiRP import AsyncPPPBridge
from security import SecurityManager
from monitoring import MonitoringManager
from connection_pool import ConnectionPool
from error_recovery import ErrorRecoveryManager

logger = logging.getLogger(__name__)

class PyLiRPApplication:
    """Main application class integrating all components"""
    
    def __init__(self, config_file: str = None, environment: str = None, mode: str = 'host'):
        self.config_manager = ConfigManager()
        self.config = None
        self.config_file = config_file
        self.environment = environment
        self.mode = mode
        
        # Core components
        self.ppp_bridge = None
        self.security_manager = None
        self.monitoring_manager = None
        self.connection_pool = None
        self.error_recovery_manager = None
        
        # Application state
        self.running = False
        self.shutdown_event = asyncio.Event()
        
    async def initialize(self):
        """Initialize all application components"""
        try:
            # Windows-specific initialization
            if platform.system() == 'Windows':
                await self._init_windows_support()
            
            # Load configuration
            logger.info(f"Loading configuration in {self.mode} mode...")
            self.config = self._load_configuration()
            
            # Setup logging based on configuration
            self._setup_logging()
            
            # Initialize components
            await self._init_security()
            await self._init_monitoring()
            await self._init_connection_pool()
            await self._init_error_recovery()
            await self._init_ppp_bridge()
            
            # Integrate components
            self._integrate_components()
            
            logger.info("All components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            raise
    
    async def _init_windows_support(self):
        """Initialize Windows-specific support"""
        from windows_support import get_windows_manager
        windows_manager = get_windows_manager()
        
        if windows_manager:
            logger.info("Initializing Windows support...")
            use_firewall = windows_manager.platform_manager.admin_privileges
            await windows_manager.setup_windows_environment({
                'setup_firewall': use_firewall,
                'optimize_performance': True
            })
            
            # Use Windows default config path if no config specified
            if not self.config_file:
                paths = windows_manager.platform_manager.get_default_paths()
                default_config = paths['config_dir'] / 'config.yaml'
                if default_config.exists():
                    self.config_file = str(default_config)
    
    def _load_configuration(self):
        """Load configuration from file"""
        config = self.config_manager.load_config(self.config_file, self.environment, self.mode)
        config.mode = self.mode  # Store mode in config
        return config
    
    async def _init_security(self):
        """Initialize security manager"""
        logger.info("Initializing security manager...")
        security_config = {
            'enabled': True,
            'allowed_ports': self.config.security.allowed_ports,
            'blocked_ips': self.config.security.blocked_ips,
            'rate_limiting': {
                'connections_per_second': self.config.security.rate_limiting.connections_per_second,
                'burst_size': self.config.security.rate_limiting.burst_size,
                'window_size': self.config.security.rate_limiting.window_size
            },
            'connection_limits': {
                'per_service_max': self.config.security.connection_limits.per_service_max
            },
            'audit_log_file': self.config.logging.file.path.replace('.log', '_security.log')
        }
        self.security_manager = SecurityManager(security_config)
    
    async def _init_monitoring(self):
        """Initialize monitoring manager"""
        logger.info("Initializing monitoring...")
        monitoring_config = {
            'metrics_port': self.config.monitoring.metrics_port,
            'enable_metrics': self.config.monitoring.enable_metrics,
            'stats_interval': self.config.monitoring.performance.stats_interval,
            'packet_capture': {
                'enabled': self.config.monitoring.packet_capture.enabled,
                'pcap_file': self.config.monitoring.packet_capture.pcap_file,
                'max_packets': 10000
            }
        }
        self.monitoring_manager = MonitoringManager(monitoring_config)
        await self.monitoring_manager.start()
    
    async def _init_connection_pool(self):
        """Initialize connection pool"""
        logger.info("Initializing connection pool...")
        self.connection_pool = ConnectionPool(
            max_connections=self.config.security.connection_limits.global_max_connections,
            idle_timeout=300,
            max_connection_age=3600
        )
        
        # Set per-service limits
        for port, service_config in self.config.services.items():
            if service_config.enabled:
                self.connection_pool.set_service_limit(
                    service_config.host, 
                    service_config.port, 
                    service_config.max_connections
                )
    
    async def _init_error_recovery(self):
        """Initialize error recovery manager"""
        logger.info("Initializing error recovery...")
        error_config = {
            'max_retry_attempts': self.config.error_recovery.max_service_retry_attempts,
            'retry_base_delay': self.config.error_recovery.service_retry_delay,
            'circuit_breaker': {
                'failure_threshold': self.config.error_recovery.circuit_breaker.failure_threshold,
                'recovery_timeout': self.config.error_recovery.circuit_breaker.recovery_timeout,
                'half_open_max_calls': self.config.error_recovery.circuit_breaker.half_open_max_calls
            }
        }
        self.error_recovery_manager = ErrorRecoveryManager(error_config)
        await self.error_recovery_manager.start_monitoring()
    
    async def _init_ppp_bridge(self):
        """Initialize PPP bridge"""
        logger.info("Initializing PPP bridge...")
        socks_host = self.config.proxy.host if self.config.proxy.enabled else None
        socks_port = self.config.proxy.port if self.config.proxy.enabled else None
        
        self.ppp_bridge = AsyncPPPBridge(
            self.config.serial.port,
            self.config.serial.baudrate,
            socks_host,
            socks_port,
            config=self.config
        )
    
    def _setup_logging(self):
        """Setup logging based on configuration"""
        # Set root log level
        logging.getLogger().setLevel(getattr(logging, self.config.logging.level))
        
        # Clear existing handlers
        logging.getLogger().handlers.clear()
        
        # Console logging
        if self.config.logging.console.enabled:
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(self.config.logging.format)
            console_handler.setFormatter(console_formatter)
            logging.getLogger().addHandler(console_handler)
        
        # File logging
        if self.config.logging.file.enabled:
            from logging.handlers import RotatingFileHandler
            
            # Ensure log directory exists
            log_path = Path(self.config.logging.file.path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Parse max size
            max_size = self.config.logging.file.max_size
            if max_size.endswith('MB'):
                max_bytes = int(max_size[:-2]) * 1024 * 1024
            elif max_size.endswith('GB'):
                max_bytes = int(max_size[:-2]) * 1024 * 1024 * 1024
            else:
                max_bytes = int(max_size)
            
            file_handler = RotatingFileHandler(
                self.config.logging.file.path,
                maxBytes=max_bytes,
                backupCount=self.config.logging.file.rotate_count
            )
            file_formatter = logging.Formatter(self.config.logging.format)
            file_handler.setFormatter(file_formatter)
            logging.getLogger().addHandler(file_handler)
        
        # Component-specific logging levels
        for component, level in self.config.logging.components.items():
            logging.getLogger(component).setLevel(getattr(logging, level))
    
    def _integrate_components(self):
        """Integrate enhancement components with PPP bridge"""
        # This would integrate the security, monitoring, connection pool,
        # and error recovery components with the main PPP bridge
        logger.info("Components integrated with PPP bridge")
    
    async def start(self):
        """Start the application"""
        try:
            logger.info("Starting PyLiRP application...")
            
            await self.initialize()
            
            # Setup signal handlers
            self._setup_signal_handlers()
            
            # Start the main PPP bridge
            logger.info("Starting PPP bridge...")
            self.running = True
            
            # Run the PPP bridge
            bridge_task = asyncio.create_task(self.ppp_bridge.run())
            shutdown_task = asyncio.create_task(self.shutdown_event.wait())
            
            # Wait for either the bridge to complete or shutdown signal
            done, pending = await asyncio.wait(
                [bridge_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            logger.info("PyLiRP application stopped")
            
        except Exception as e:
            logger.error(f"Application error: {e}")
            raise
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Shutdown the application cleanly"""
        if not self.running:
            return
        
        logger.info("Shutting down PyLiRP application...")
        self.running = False
        
        # Shutdown components in reverse order
        if self.error_recovery_manager:
            await self.error_recovery_manager.stop_monitoring()
        
        if self.connection_pool:
            await self.connection_pool.shutdown()
        
        if self.monitoring_manager:
            await self.monitoring_manager.stop()
        
        if self.security_manager:
            await self.security_manager.shutdown()
        
        logger.info("PyLiRP application shutdown complete")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        import signal
        
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            if platform.system() == 'Windows':
                from windows_support import get_windows_manager
                windows_manager = get_windows_manager()
                if windows_manager:
                    windows_manager.log_event('info', f'Received shutdown signal {signum}')
            self.shutdown_event.set()
        
        # Windows doesn't support SIGTERM, use different signals
        if platform.system() == 'Windows':
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGBREAK, signal_handler)
        else:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)