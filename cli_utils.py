#!/usr/bin/env python3
"""
CLI Utilities for PyLiRP
Command line argument parsing and validation functions
"""

import argparse
import platform
import logging
import sys

from config_manager import ConfigManager

logger = logging.getLogger(__name__)

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
        '-m', '--mode',
        choices=['host', 'client'],
        default='host',
        help='Operation mode: host (server with services) or client (initiates connections)'
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
    
    parser.add_argument(
        '--testfor',
        type=int,
        metavar='SECONDS',
        help='Maximum execution time in seconds before clean exit'
    )
    
    parser.add_argument(
        '--exit-on-peer-disconnect',
        action='store_true',
        help='Exit cleanly when peer disconnects after successful connection'
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

def check_virtual_environment():
    """Check if running in virtual environment and log info"""
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    
    if in_venv:
        venv_path = sys.prefix
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

async def handle_windows_commands(args):
    """Handle Windows-specific command line arguments"""
    from windows_support import get_windows_manager
    import os
    
    windows_manager = get_windows_manager()
    if not windows_manager:
        return False
    
    if hasattr(args, 'list_com_ports') and args.list_com_ports:
        print("Available COM ports:")
        ports = windows_manager.platform_manager.get_com_ports()
        if ports:
            for port in ports:
                print(f"  {port['device']}: {port['description']}")
        else:
            print("  No COM ports found")
        return True
    
    if hasattr(args, 'install_service') and args.install_service:
        script_path = os.path.abspath(sys.argv[0])
        paths = windows_manager.platform_manager.get_default_paths(
            portable=False, 
            admin_mode=not args.userspace if hasattr(args, 'userspace') else None
        )
        config_path = args.config or os.path.join(paths['config_dir'], 'config.yaml')
        
        # Use userspace mode if no admin privileges or explicitly requested
        use_userspace = (hasattr(args, 'userspace') and args.userspace) or \
                       not windows_manager.platform_manager.admin_privileges
        
        success = await windows_manager.service_manager.install_service(
            script_path, config_path, userspace=use_userspace, method='service'
        )
        if success:
            service_type = "userspace service" if use_userspace else "Windows service"
            print(f"{service_type} installed successfully")
            windows_manager.show_notification(
                "PyLiRP", f"{service_type} installed successfully", "info"
            )
        else:
            print("Failed to install service")
        return True
    
    if hasattr(args, 'install_task') and args.install_task:
        script_path = os.path.abspath(sys.argv[0])
        paths = windows_manager.platform_manager.get_default_paths(portable=False)
        config_path = args.config or os.path.join(paths['config_dir'], 'config.yaml')
        
        success = await windows_manager.service_manager.install_service(
            script_path, config_path, userspace=True, method='task'
        )
        if success:
            print("Windows scheduled task installed successfully")
            print("Task name: PyLiRP-UserSpace")
        else:
            print("Failed to install scheduled task")
        return True
    
    if hasattr(args, 'uninstall_service') and args.uninstall_service:
        success = await windows_manager.uninstall_service()
        if success:
            print("Windows service uninstalled successfully")
        else:
            print("Failed to uninstall Windows service")
        return True
    
    return False