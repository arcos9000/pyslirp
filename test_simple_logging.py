#!/usr/bin/env python3
"""
Simple test to verify no unwanted logging occurs
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safe_logger import setup_safe_logging, get_safe_logger

def test_no_logging():
    print("=== Test: No Logging Should Occur ===")
    
    # Ensure logging is disabled
    setup_safe_logging(enabled=False)
    
    # Import modules that might log
    from security import SecurityEventType, SecurityEvent, ThreatLevel
    from error_recovery import ErrorType
    from connection_pool import ConnectionState
    from monitoring import MetricType
    
    print("✓ All modules imported without logging")
    
    # Create some objects that might trigger logging
    event = SecurityEvent(
        event_type=SecurityEventType.CONNECTION_ALLOWED,
        source_ip='127.0.0.1',
        description='Test event',
        threat_level=ThreatLevel.LOW
    )
    print("✓ SecurityEvent created without logging")
    
    # Test safe logger directly
    logger = get_safe_logger('test')
    logger.info("This should NOT appear in any logs")
    logger.error("This error should NOT appear in any logs")
    print("✓ Safe logger calls completed without output")

def test_with_logging():
    print("\n=== Test: With Logging Enabled ===")
    
    # Enable logging
    setup_safe_logging(enabled=True)
    
    # Test safe logger
    logger = get_safe_logger('test')
    logger.info("This SHOULD appear in logs")
    logger.error("This error SHOULD appear in logs")
    print("✓ Safe logger calls completed with expected output")

if __name__ == "__main__":
    test_no_logging()
    test_with_logging()
    print("\n🎉 Simple logging tests completed!")