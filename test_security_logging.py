#!/usr/bin/env python3
"""
Test security manager logging behavior
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safe_logger import setup_safe_logging
from security import SecurityManager

def test_security_without_logging():
    print("=== Test Security Without Logging ===")
    
    # Don't enable logging
    setup_safe_logging(enabled=False)
    
    # Create security manager
    config = {
        'enabled': True,
        'allowed_ports': [22, 80, 443],
        'blocked_ips': [],
        'rate_limit': {
            'enabled': True,
            'requests_per_second': 10,
            'burst_size': 20
        },
        'connection_limits': {
            'max_connections_per_ip': 5,
            'max_total_connections': 50
        },
        'audit_logging': {
            'enabled': False,  # Disabled
            'log_file': None
        }
    }
    
    try:
        security_manager = SecurityManager(config)
        print("✓ Security manager created without logging errors")
        
        # Test a security check
        result = security_manager.check_connection_allowed('127.0.0.1', 22)
        print(f"✓ Connection check result: {result}")
        
    except Exception as e:
        print(f"✗ Security manager failed: {e}")
        import traceback
        traceback.print_exc()

def test_security_with_logging():
    print("\n=== Test Security With Logging ===")
    
    # Enable logging
    setup_safe_logging(enabled=True)
    
    # Create security manager
    config = {
        'enabled': True,
        'allowed_ports': [22, 80, 443],
        'blocked_ips': [],
        'rate_limit': {
            'enabled': True,
            'requests_per_second': 10,
            'burst_size': 20
        },
        'connection_limits': {
            'max_connections_per_ip': 5,
            'max_total_connections': 50
        },
        'audit_logging': {
            'enabled': False,  # Still disabled for safety
            'log_file': None
        }
    }
    
    try:
        security_manager = SecurityManager(config)
        print("✓ Security manager created with logging enabled")
        
        # Test a security check
        result = security_manager.check_connection_allowed('127.0.0.1', 22)
        print(f"✓ Connection check result: {result}")
        
    except Exception as e:
        print(f"✗ Security manager failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_security_without_logging()
    test_security_with_logging()
    print("\n🎉 Security logging tests completed!")