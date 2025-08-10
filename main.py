#!/usr/bin/env python3
"""
PyLiRP Main Entry Point (Simplified)
"""

import asyncio
import logging
import sys
import os
import platform

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import PyLiRPApplication
from cli_utils import (
    create_argument_parser,
    validate_configuration,
    test_serial_port,
    check_virtual_environment,
    handle_windows_commands
)
from config_manager import Config, SerialConfig, ProxyConfig

logger = logging.getLogger(__name__)

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
    if platform.system() == 'Windows':
        if await handle_windows_commands(args):
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
        app = PyLiRPApplication(args.config, args.environment, args.mode)
        
        # Override config with command line arguments if provided
        if args.serial_port and not args.config:
            # Create minimal config for command-line usage
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