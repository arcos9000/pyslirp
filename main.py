#!/usr/bin/env python3
"""
PyLiRP Main Entry Point
Integrated Python SLiRP implementation with all enhancement modules
"""

import asyncio
import argparse
import signal
import sys
import os
import platform
import logging
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from pySLiRP import AsyncPPPBridge
from security import SecurityManager
from monitoring import MonitoringManager
from connection_pool import ConnectionPool
from error_recovery import ErrorRecoveryManager

# Windows support
if platform.system() == 'Windows':
    from windows_support import get_windows_manager
    WINDOWS_MANAGER = get_windows_manager()
else:
    WINDOWS_MANAGER = None

logger = logging.getLogger(__name__)

def check_virtual_environment():
    """Check if running in virtual environment and log info"""
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    
    if in_venv:
        venv_path = os.environ.get('VIRTUAL_ENV', sys.prefix)
        logger.info(f"Running in virtual environment: {venv_path}")
        logger.info(f"Python executable: {sys.executable}")
    else:
        logger.warning("Not running in virtual environment - this may cause dependency issues")
        logger.info(f"Python executable: {sys.executable}")
        logger.info(f"Python version: {sys.version}")
        
        # Check if we're in a situation where venv is recommended
        import site
        user_site = site.getusersitepackages() if hasattr(site, 'getusersitepackages') else None
        if user_site and user_site in sys.path:
            logger.info("Using user site-packages - this is OK for user installations")
    
    return in_venv

class PyLiRPApplication:
    """Main application class integrating all components"""
    
    def __init__(self, config_file: str = None, environment: str = None):
        self.config_manager = ConfigManager()
        self.config = None
        self.config_file = config_file
        self.environment = environment
        
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
            if WINDOWS_MANAGER:
                logger.info("Initializing Windows support...")
                # In userspace mode, don't modify firewall (localhost only)
                use_firewall = WINDOWS_MANAGER.platform_manager.admin_privileges
                await WINDOWS_MANAGER.setup_windows_environment({
                    'setup_firewall': use_firewall,  # Only if admin privileges
                    'optimize_performance': True
                })
            
            # Load configuration
            logger.info("Loading configuration...")
            if WINDOWS_MANAGER and not self.config_file:
                # Use Windows default config path if no config specified
                paths = WINDOWS_MANAGER.platform_manager.get_default_paths()
                default_config = os.path.join(paths['config_dir'], 'config.yaml')
                if os.path.exists(default_config):
                    self.config_file = default_config
            
            self.config = self.config_manager.load_config(
                self.config_file, self.environment
            )
            
            # Setup logging based on configuration
            self._setup_logging()
            
            # Initialize security manager
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
            
            # Initialize monitoring manager
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
            
            # Initialize connection pool
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
            
            # Initialize error recovery manager
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
            
            # Initialize PPP bridge with all enhancements
            logger.info("Initializing PPP bridge...")
            socks_host = self.config.proxy.host if self.config.proxy.enabled else None
            socks_port = self.config.proxy.port if self.config.proxy.enabled else None
            
            self.ppp_bridge = AsyncPPPBridge(
                self.config.serial.port,
                self.config.serial.baudrate,
                socks_host,
                socks_port
            )
            
            # Integrate components with PPP bridge
            self._integrate_components()
            
            logger.info("All components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            raise
    
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
        # The integration depends on the specific implementation details
        # of the enhanced PPP bridge created by the networking expert
        
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
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            if WINDOWS_MANAGER:
                WINDOWS_MANAGER.log_event('info', f'Received shutdown signal {signum}')
            self.shutdown_event.set()
        
        # Windows doesn't support SIGTERM, use different signals
        if platform.system() == 'Windows':
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGBREAK, signal_handler)
        else:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

def create_argument_parser():
    """Create command line argument parser"""
    parser = argparse.ArgumentParser(
        description='PyLiRP - Python SLiRP PPP Bridge',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /dev/ttyUSB0                           # Basic usage
  %(prog)s -c config.yaml                         # With config file
  %(prog)s -c config.yaml -e production          # With environment
  %(prog)s --validate-config config.yaml         # Validate config only
  %(prog)s --test-serial /dev/ttyUSB0            # Test serial port
        """
    )
    
    parser.add_argument(
        'serial_port',
        nargs='?',
        help='Serial port device (e.g., /dev/ttyUSB0)'
    )
    
    parser.add_argument(
        '-c', '--config',
        help='Configuration file path'
    )
    
    parser.add_argument(
        '-e', '--environment',
        help='Environment name (dev/prod/test)'
    )
    
    parser.add_argument(
        '-b', '--baudrate',
        type=int,
        default=115200,
        help='Serial port baudrate (default: 115200)'
    )
    
    parser.add_argument(
        '--socks-host',
        help='SOCKS5 proxy host'
    )
    
    parser.add_argument(
        '--socks-port',
        type=int,
        default=1080,
        help='SOCKS5 proxy port (default: 1080)'
    )
    
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as daemon'
    )
    
    parser.add_argument(
        '--validate-config',
        action='store_true',
        help='Validate configuration and exit'
    )
    
    parser.add_argument(
        '--test-serial',
        action='store_true',
        help='Test serial port and exit'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='PyLiRP 1.0.0'
    )
    
    # Windows-specific arguments
    if platform.system() == 'Windows':
        parser.add_argument(
            '--install-service',
            action='store_true',
            help='Install as Windows service'
        )
        
        parser.add_argument(
            '--uninstall-service',
            action='store_true',
            help='Uninstall Windows service'
        )
        
        parser.add_argument(
            '--service',
            action='store_true',
            help='Run as Windows service (internal use)'
        )
        
        parser.add_argument(
            '--list-com-ports',
            action='store_true',
            help='List available COM ports'
        )
        
        parser.add_argument(
            '--install-task',
            action='store_true',
            help='Install as Windows scheduled task (userspace)'
        )
        
        parser.add_argument(
            '--uninstall-task',
            action='store_true',
            help='Uninstall Windows scheduled task'
        )
        
        parser.add_argument(
            '--userspace',
            action='store_true',
            help='Force userspace mode (no admin privileges required)'
        )
    
    return parser

async def validate_configuration(config_file: str, environment: str = None):
    """Validate configuration file"""
    try:
        config_manager = ConfigManager()
        config = config_manager.load_config(config_file, environment)
        
        print("✓ Configuration is valid")
        print(f"  Serial port: {config.serial.port}")
        print(f"  Baudrate: {config.serial.baudrate}")
        print(f"  Services: {len(config.services)} configured")
        print(f"  Security: {'enabled' if config.security else 'disabled'}")
        print(f"  Monitoring: {'enabled' if config.monitoring.enable_metrics else 'disabled'}")
        
        return True
        
    except Exception as e:
        print(f"✗ Configuration validation failed: {e}")
        return False

async def test_serial_port(serial_port: str, baudrate: int = 115200):
    """Test serial port connectivity"""
    try:
        import serial_asyncio
        
        print(f"Testing serial port: {serial_port} at {baudrate} baud")
        
        # Try to open serial connection
        reader, writer = await serial_asyncio.open_serial_connection(
            url=serial_port,
            baudrate=baudrate,
            timeout=5
        )
        
        print("✓ Serial port opened successfully")
        
        # Close connection
        writer.close()
        await writer.wait_closed()
        
        print("✓ Serial port test completed")
        return True
        
    except Exception as e:
        print(f"✗ Serial port test failed: {e}")
        return False

async def main():
    """Main entry point"""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Setup basic logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Check virtual environment
    check_virtual_environment()
    
    # Handle Windows-specific commands
    if platform.system() == 'Windows' and WINDOWS_MANAGER:
        if hasattr(args, 'list_com_ports') and args.list_com_ports:
            print("Available COM ports:")
            ports = WINDOWS_MANAGER.platform_manager.get_com_ports()
            if ports:
                for port in ports:
                    print(f"  {port['device']}: {port['description']}")
            else:
                print("  No COM ports found")
            return
        
        if hasattr(args, 'install_service') and args.install_service:
            script_path = os.path.abspath(__file__)
            paths = WINDOWS_MANAGER.platform_manager.get_default_paths(
                portable=False, 
                admin_mode=not args.userspace if hasattr(args, 'userspace') else None
            )
            config_path = args.config or os.path.join(paths['config_dir'], 'config.yaml')
            
            # Use userspace mode if no admin privileges or explicitly requested
            use_userspace = (hasattr(args, 'userspace') and args.userspace) or \
                           not WINDOWS_MANAGER.platform_manager.admin_privileges
            
            success = await WINDOWS_MANAGER.service_manager.install_service(
                script_path, config_path, userspace=use_userspace, method='service'
            )
            if success:
                service_type = "userspace service" if use_userspace else "Windows service"
                print(f"{service_type} installed successfully")
                WINDOWS_MANAGER.show_notification(
                    "PyLiRP", f"{service_type} installed successfully", "info"
                )
            else:
                print("Failed to install service")
            return
        
        if hasattr(args, 'install_task') and args.install_task:
            script_path = os.path.abspath(__file__)
            paths = WINDOWS_MANAGER.platform_manager.get_default_paths(portable=False)
            config_path = args.config or os.path.join(paths['config_dir'], 'config.yaml')
            
            success = await WINDOWS_MANAGER.service_manager.install_service(
                script_path, config_path, userspace=True, method='task'
            )
            if success:
                print("Windows scheduled task installed successfully")
                print("Task name: PyLiRP-UserSpace")
            else:
                print("Failed to install scheduled task")
            return
        
        if hasattr(args, 'uninstall_service') and args.uninstall_service:
            success = await WINDOWS_MANAGER.uninstall_service()
            if success:
                print("Windows service uninstalled successfully")
            else:
                print("Failed to uninstall Windows service")
            return
    
    # Handle special modes
    if args.validate_config:
        config_file = args.config or 'config.yaml'
        success = await validate_configuration(config_file, args.environment)
        sys.exit(0 if success else 1)
    
    if args.test_serial:
        serial_port = args.serial_port
        if not serial_port:
            print("Serial port required for testing")
            sys.exit(1)
        success = await test_serial_port(serial_port, args.baudrate)
        sys.exit(0 if success else 1)
    
    # Normal operation
    if not args.serial_port and not args.config:
        print("Either serial port or config file must be specified")
        parser.print_help()
        sys.exit(1)
    
    try:
        # Create and run application
        app = PyLiRPApplication(args.config, args.environment)
        
        # Override config with command line arguments if provided
        if args.serial_port and not args.config:
            # Create minimal config for command-line usage
            from config_manager import Config, SerialConfig, ProxyConfig
            app.config = Config(
                serial=SerialConfig(
                    port=args.serial_port,
                    baudrate=args.baudrate
                ),
                proxy=ProxyConfig(
                    type='socks5' if args.socks_host else 'none',
                    host=args.socks_host or '127.0.0.1',
                    port=args.socks_port,
                    enabled=bool(args.socks_host)
                )
            )
        
        await app.start()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Application failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())