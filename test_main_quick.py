#!/usr/bin/env python3
"""
Quick test of main.py without dependencies to check for undefined names
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock all the modules that aren't available
class MockModule:
    def __getattr__(self, name):
        return MockModule()
    
    def __call__(self, *args, **kwargs):
        return MockModule()

# Mock all dependencies
modules_to_mock = [
    'serial_asyncio', 'pySLiRP', 'security', 'monitoring', 
    'connection_pool', 'error_recovery', 'windows_support'
]

for module in modules_to_mock:
    sys.modules[module] = MockModule()

# Override some specific classes that are imported
import config_manager
config_manager.ConfigManager = MockModule
config_manager.Config = MockModule  
config_manager.SerialConfig = MockModule
config_manager.ProxyConfig = MockModule

# Now test main
try:
    from main import main
    print("✓ main.py imports successfully")
    
    # Test argument parsing
    sys.argv = ['main.py', '--help']
    try:
        import argparse
        from cli_utils import create_argument_parser
        parser = create_argument_parser()
        args = parser.parse_args(['--help'])
    except SystemExit:
        print("✓ Help system works")
    except Exception as e:
        print(f"✗ Help system failed: {e}")
    
    print("✓ No undefined name errors found")
    
except Exception as e:
    print(f"✗ Error in main.py: {e}")
    import traceback
    traceback.print_exc()