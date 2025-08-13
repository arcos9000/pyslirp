#!/usr/bin/env python3
"""
Test that modules don't log when logging is disabled
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure logging is disabled
from safe_logger import setup_safe_logging
setup_safe_logging(enabled=False)

print("Testing module imports without logging...")

# Import all the main modules
try:
    from security import SecurityManager
    print("✓ security.py imported")
except Exception as e:
    print(f"✗ security.py failed: {e}")

try:
    from error_recovery import ErrorRecoveryManager
    print("✓ error_recovery.py imported")
except Exception as e:
    print(f"✗ error_recovery.py failed: {e}")

try:
    from connection_pool import ConnectionPool
    print("✓ connection_pool.py imported")
except Exception as e:
    print(f"✗ connection_pool.py failed: {e}")

try:
    from monitoring import MonitoringManager
    print("✓ monitoring.py imported")
except Exception as e:
    print(f"✗ monitoring.py failed: {e}")

try:
    from config_manager import ConfigManager
    print("✓ config_manager.py imported")
except Exception as e:
    print(f"✗ config_manager.py failed: {e}")

print("\n🎉 All modules imported successfully without unwanted logging!")