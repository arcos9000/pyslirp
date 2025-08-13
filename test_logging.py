#!/usr/bin/env python3
"""
Test script for safe logging functionality
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safe_logger import setup_safe_logging, get_safe_logger, is_logging_enabled

def test_logging_disabled():
    """Test with logging disabled"""
    print("=== Test 1: Logging Disabled ===")
    
    # Setup with logging disabled
    result = setup_safe_logging(enabled=False)
    print(f"Setup result: {result}")
    print(f"Is logging enabled: {is_logging_enabled()}")
    
    # Get logger and try to log
    logger = get_safe_logger("test")
    logger.info("This should not appear in logs")
    logger.error("This error should not appear in logs")
    
    print("✓ Logging disabled test completed")

def test_logging_enabled():
    """Test with logging enabled"""
    print("\n=== Test 2: Logging Enabled ===")
    
    # Setup with logging enabled
    result = setup_safe_logging(enabled=True)
    print(f"Setup result: {result}")
    print(f"Is logging enabled: {is_logging_enabled()}")
    
    if result:
        # Get logger and try to log
        logger = get_safe_logger("test")
        logger.info("This should appear in logs if logging works")
        logger.error("This error should appear in logs if logging works")
        print("✓ Logging enabled test completed")
    else:
        print("✗ Logging setup failed (expected on systems with permission issues)")

def test_permission_failure():
    """Test logging failure due to permissions"""
    print("\n=== Test 3: Simulated Permission Failure ===")
    
    # Temporarily override test locations to cause failure
    import safe_logger
    original_test = safe_logger.test_log_writability
    
    def mock_test():
        return False
    
    safe_logger.test_log_writability = mock_test
    
    # Try to setup logging
    result = setup_safe_logging(enabled=True)
    print(f"Setup result with mock failure: {result}")
    print(f"Is logging enabled: {is_logging_enabled()}")
    
    # Restore original function
    safe_logger.test_log_writability = original_test
    
    print("✓ Permission failure test completed")

if __name__ == "__main__":
    test_logging_disabled()
    test_logging_enabled() 
    test_permission_failure()
    print("\n🎉 All logging tests completed!")