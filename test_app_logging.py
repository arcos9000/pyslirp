#!/usr/bin/env python3
"""
Test app.py logging functionality without dependencies
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safe_logger import setup_safe_logging

# Mock the missing modules
class MockModule:
    def __getattr__(self, name):
        return MockModule()
    
    def __call__(self, *args, **kwargs):
        return MockModule()

sys.modules['serial_asyncio'] = MockModule()
sys.modules['pySLiRP'] = MockModule()
sys.modules['security'] = MockModule() 
sys.modules['monitoring'] = MockModule()
sys.modules['connection_pool'] = MockModule()
sys.modules['error_recovery'] = MockModule()
sys.modules['config_manager'] = MockModule()

# Now import app
from app import PyLiRPApplication

def test_app_without_logging():
    print("=== Test App Without Logging ===")
    
    # Don't enable logging
    setup_safe_logging(enabled=False)
    
    # Create app instance
    app = PyLiRPApplication()
    
    # Test log_or_print method
    app._log_or_print("info", "This should print to console")
    app._log_or_print("error", "This error should print to console")
    
    print("✓ App created and logging works without crashing")

def test_app_with_logging():
    print("\n=== Test App With Logging ===")
    
    # Enable logging
    result = setup_safe_logging(enabled=True)
    print(f"Logging setup result: {result}")
    
    # Create app instance
    app = PyLiRPApplication()
    
    # Test log_or_print method
    app._log_or_print("info", "This should appear in logs")
    app._log_or_print("error", "This error should appear in logs")
    
    print("✓ App created and logging works with logging enabled")

if __name__ == "__main__":
    test_app_without_logging()
    test_app_with_logging()
    print("\n🎉 All app logging tests passed!")