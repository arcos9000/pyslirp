#!/usr/bin/env python3
"""
Safe Logger Wrapper for PyLiRP
Provides logging with graceful error handling to prevent crashes
"""

import logging
import sys
from typing import Any, Optional

class SafeLogger:
    """
    Safe logger wrapper that prevents logging errors from crashing the application.
    Can be completely disabled to avoid permission issues on systems like PiKVM.
    """
    
    def __init__(self, name: str, enabled: bool = False):
        self.name = name
        self.enabled = enabled
        self._logger = None
        
        if self.enabled:
            try:
                self._logger = logging.getLogger(name)
            except Exception:
                self.enabled = False
                self._logger = None
    
    def _safe_log(self, level: int, msg: Any, *args, **kwargs):
        """Safely log a message, ignoring any errors"""
        if not self.enabled or not self._logger:
            return
            
        try:
            self._logger.log(level, msg, *args, **kwargs)
        except Exception:
            # Silently ignore logging errors to prevent crashes
            pass
    
    def debug(self, msg: Any, *args, **kwargs):
        """Log debug message safely"""
        self._safe_log(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: Any, *args, **kwargs):
        """Log info message safely"""
        self._safe_log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: Any, *args, **kwargs):
        """Log warning message safely"""
        self._safe_log(logging.WARNING, msg, *args, **kwargs)
    
    def warn(self, msg: Any, *args, **kwargs):
        """Alias for warning"""
        self.warning(msg, *args, **kwargs)
    
    def error(self, msg: Any, *args, **kwargs):
        """Log error message safely"""
        self._safe_log(logging.ERROR, msg, *args, **kwargs)
    
    def exception(self, msg: Any, *args, exc_info=True, **kwargs):
        """Log exception safely"""
        self._safe_log(logging.ERROR, msg, *args, exc_info=exc_info, **kwargs)
    
    def critical(self, msg: Any, *args, **kwargs):
        """Log critical message safely"""
        self._safe_log(logging.CRITICAL, msg, *args, **kwargs)

# Global logging state
_logging_enabled = False
_loggers = {}

def test_log_writability() -> bool:
    """
    Test if we can write to common log locations.
    
    Returns:
        True if logging appears to be working, False otherwise
    """
    import tempfile
    import os
    
    # Test locations in order of preference
    test_locations = [
        '/tmp/pyslirp_test.log',
        '/var/log/pyslirp_test.log', 
        os.path.expanduser('~/pyslirp_test.log'),
        tempfile.gettempdir() + '/pyslirp_test.log'
    ]
    
    for location in test_locations:
        try:
            # Try to create and write to test file
            with open(location, 'w') as f:
                f.write('test')
            # Clean up
            os.unlink(location)
            return True
        except (OSError, IOError, PermissionError):
            continue
    
    return False

def setup_safe_logging(enabled: bool = False, level: int = logging.INFO) -> bool:
    """
    Setup safe logging system with writability test.
    
    Args:
        enabled: Whether to enable logging at all
        level: Logging level (only used if enabled=True)
        
    Returns:
        True if logging was successfully enabled, False otherwise
    """
    global _logging_enabled
    _logging_enabled = False  # Start disabled
    
    if not enabled:
        return False
    
    # Test if we can actually write logs
    if not test_log_writability():
        print("Warning: Cannot write to log files - logging disabled")
        return False
    
    try:
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        _logging_enabled = True
        return True
    except Exception as e:
        print(f"Warning: Logging setup failed ({e}) - logging disabled")
        return False

def get_safe_logger(name: str) -> SafeLogger:
    """
    Get a safe logger instance.
    
    Args:
        name: Logger name
        
    Returns:
        SafeLogger instance
    """
    if name not in _loggers:
        _loggers[name] = SafeLogger(name, _logging_enabled)
    return _loggers[name]

def is_logging_enabled() -> bool:
    """Check if logging is currently enabled"""
    return _logging_enabled

# Convenience function for backwards compatibility
def getLogger(name: str) -> SafeLogger:
    """Get a safe logger (backwards compatible with logging.getLogger)"""
    return get_safe_logger(name)