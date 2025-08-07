#!/usr/bin/env python3
"""
Error Recovery and Resilience Framework for PyLiRP
Provides comprehensive error handling, recovery mechanisms, and system resilience
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import defaultdict, deque
import traceback

logger = logging.getLogger(__name__)

class ErrorType(Enum):
    """Types of errors that can occur"""
    SERIAL_ERROR = auto()
    NETWORK_ERROR = auto()
    PROTOCOL_ERROR = auto()
    SERVICE_ERROR = auto()
    CONFIGURATION_ERROR = auto()
    MEMORY_ERROR = auto()
    TIMEOUT_ERROR = auto()
    AUTHENTICATION_ERROR = auto()
    SYSTEM_ERROR = auto()

class RecoveryAction(Enum):
    """Types of recovery actions"""
    RETRY = auto()
    RECONNECT = auto()
    RESET = auto()
    FAILOVER = auto()
    DEGRADE = auto()
    SHUTDOWN = auto()
    IGNORE = auto()

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = auto()     # Normal operation
    OPEN = auto()       # Failing, rejecting calls
    HALF_OPEN = auto()  # Testing if service recovered

@dataclass
class ErrorEvent:
    """Represents an error event"""
    error_type: ErrorType
    timestamp: float
    description: str
    component: str
    exception: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        return {
            'error_type': self.error_type.name,
            'timestamp': self.timestamp,
            'description': self.description,
            'component': self.component,
            'exception': str(self.exception) if self.exception else None,
            'metadata': self.metadata
        }

@dataclass
class RecoveryAttempt:
    """Tracks a recovery attempt"""
    timestamp: float
    action: RecoveryAction
    success: bool
    duration: float = 0.0
    details: str = ""

class CircuitBreaker:
    """Circuit breaker for service protection"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, 
                 half_open_max_calls: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0
        
        # Statistics
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.circuit_opens = 0
    
    async def call(self, func: Callable, *args, **kwargs):
        """Execute function through circuit breaker"""
        self.total_calls += 1
        
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                raise Exception("Circuit breaker is OPEN - calls rejected")
        
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                raise Exception("Circuit breaker HALF_OPEN limit reached")
            self.half_open_calls += 1
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
            
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call"""
        self.successful_calls += 1
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info("Circuit breaker transitioning to CLOSED")
    
    def _on_failure(self):
        """Handle failed call"""
        self.failed_calls += 1
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if (self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN) and
            self.failure_count >= self.failure_threshold):
            self.state = CircuitState.OPEN
            self.circuit_opens += 1
            logger.warning(f"Circuit breaker transitioning to OPEN after {self.failure_count} failures")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics"""
        return {
            'state': self.state.name,
            'failure_count': self.failure_count,
            'total_calls': self.total_calls,
            'successful_calls': self.successful_calls,
            'failed_calls': self.failed_calls,
            'circuit_opens': self.circuit_opens,
            'success_rate': self.successful_calls / self.total_calls if self.total_calls > 0 else 0.0
        }

class RetryManager:
    """Manages retry logic with exponential backoff"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, 
                 max_delay: float = 60.0, backoff_factor: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    async def execute_with_retry(self, func: Callable, *args, 
                               retryable_exceptions: Tuple = (Exception,),
                               **kwargs) -> Any:
        """Execute function with retry logic"""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
                
            except retryable_exceptions as e:
                last_exception = e
                
                if attempt == self.max_retries:
                    logger.error(f"All retry attempts failed: {e}")
                    raise e
                
                # Calculate delay with exponential backoff
                delay = min(
                    self.base_delay * (self.backoff_factor ** attempt),
                    self.max_delay
                )
                
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s")
                await asyncio.sleep(delay)
            
            except Exception as e:
                # Non-retryable exception
                logger.error(f"Non-retryable exception: {e}")
                raise e
        
        # This should not be reached, but just in case
        raise last_exception or Exception("Retry logic failed unexpectedly")

class ServiceHealthTracker:
    """Tracks health of individual services"""
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._health_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=window_size)
        )
        self._last_check: Dict[str, float] = {}
        self._consecutive_failures: Dict[str, int] = defaultdict(int)
    
    def record_health_check(self, service: str, healthy: bool):
        """Record health check result"""
        self._health_history[service].append((time.time(), healthy))
        self._last_check[service] = time.time()
        
        if healthy:
            self._consecutive_failures[service] = 0
        else:
            self._consecutive_failures[service] += 1
    
    def is_healthy(self, service: str, threshold: float = 0.8) -> bool:
        """Check if service is healthy based on recent history"""
        if service not in self._health_history:
            return True  # Assume healthy if no data
        
        history = self._health_history[service]
        if not history:
            return True
        
        # Calculate success rate in recent history
        recent_checks = list(history)[-min(20, len(history)):]  # Last 20 checks
        successful = sum(1 for _, healthy in recent_checks if healthy)
        success_rate = successful / len(recent_checks)
        
        return success_rate >= threshold
    
    def get_consecutive_failures(self, service: str) -> int:
        """Get consecutive failure count"""
        return self._consecutive_failures.get(service, 0)
    
    def get_service_stats(self, service: str) -> Dict[str, Any]:
        """Get detailed service statistics"""
        if service not in self._health_history:
            return {'status': 'unknown', 'checks': 0}
        
        history = list(self._health_history[service])
        if not history:
            return {'status': 'unknown', 'checks': 0}
        
        total_checks = len(history)
        successful = sum(1 for _, healthy in history if healthy)
        success_rate = successful / total_checks
        
        # Recent trend (last 10 checks)
        recent = history[-10:] if len(history) >= 10 else history
        recent_successful = sum(1 for _, healthy in recent if healthy)
        recent_rate = recent_successful / len(recent)
        
        return {
            'status': 'healthy' if self.is_healthy(service) else 'unhealthy',
            'total_checks': total_checks,
            'success_rate': success_rate,
            'recent_success_rate': recent_rate,
            'consecutive_failures': self._consecutive_failures[service],
            'last_check': self._last_check.get(service, 0)
        }

class ConnectionRecoveryManager:
    """Manages connection recovery and failover"""
    
    def __init__(self):
        self._active_connections: Dict[str, Any] = {}
        self._backup_connections: Dict[str, List[Any]] = {}
        self._connection_health: Dict[str, bool] = {}
        self._recovery_tasks: Dict[str, asyncio.Task] = {}
    
    def register_connection(self, connection_id: str, connection: Any, 
                          backup_connections: Optional[List[Any]] = None):
        """Register a connection for monitoring"""
        self._active_connections[connection_id] = connection
        self._backup_connections[connection_id] = backup_connections or []
        self._connection_health[connection_id] = True
    
    async def check_connection_health(self, connection_id: str) -> bool:
        """Check if connection is healthy"""
        if connection_id not in self._active_connections:
            return False
        
        connection = self._active_connections[connection_id]
        
        try:
            # Implement connection-specific health check
            # This would depend on the connection type
            if hasattr(connection, 'is_alive'):
                healthy = await connection.is_alive()
            elif hasattr(connection, 'ping'):
                await connection.ping()
                healthy = True
            else:
                # Basic check - see if connection is still open
                healthy = not getattr(connection, 'is_closing', lambda: False)()
            
            self._connection_health[connection_id] = healthy
            return healthy
            
        except Exception as e:
            logger.error(f"Health check failed for {connection_id}: {e}")
            self._connection_health[connection_id] = False
            return False
    
    async def recover_connection(self, connection_id: str) -> bool:
        """Attempt to recover a failed connection"""
        if connection_id in self._recovery_tasks:
            # Recovery already in progress
            return False
        
        async def recovery_task():
            try:
                logger.info(f"Starting connection recovery for {connection_id}")
                
                # Try backup connections first
                backups = self._backup_connections.get(connection_id, [])
                for backup in backups:
                    try:
                        if await self._test_connection(backup):
                            self._active_connections[connection_id] = backup
                            self._connection_health[connection_id] = True
                            logger.info(f"Failed over to backup connection for {connection_id}")
                            return True
                    except Exception as e:
                        logger.warning(f"Backup connection failed for {connection_id}: {e}")
                        continue
                
                # Try to reconnect the original connection
                original = self._active_connections.get(connection_id)
                if original and hasattr(original, 'reconnect'):
                    try:
                        await original.reconnect()
                        if await self.check_connection_health(connection_id):
                            logger.info(f"Reconnected original connection for {connection_id}")
                            return True
                    except Exception as e:
                        logger.error(f"Reconnection failed for {connection_id}: {e}")
                
                logger.error(f"Connection recovery failed for {connection_id}")
                return False
                
            finally:
                # Clean up recovery task
                if connection_id in self._recovery_tasks:
                    del self._recovery_tasks[connection_id]
        
        self._recovery_tasks[connection_id] = asyncio.create_task(recovery_task())
        return await self._recovery_tasks[connection_id]
    
    async def _test_connection(self, connection: Any) -> bool:
        """Test if a connection is working"""
        try:
            if hasattr(connection, 'test'):
                return await connection.test()
            elif hasattr(connection, 'ping'):
                await connection.ping()
                return True
            else:
                return True  # Assume working if no test method
        except:
            return False

class ErrorRecoveryManager:
    """Main error recovery and resilience manager"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Component managers
        self.retry_manager = RetryManager(
            max_retries=config.get('max_retry_attempts', 3),
            base_delay=config.get('retry_base_delay', 1.0),
            max_delay=config.get('retry_max_delay', 60.0)
        )
        
        self.service_health_tracker = ServiceHealthTracker(
            window_size=config.get('health_window_size', 100)
        )
        
        self.connection_recovery_manager = ConnectionRecoveryManager()
        
        # Circuit breakers for different services
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Error tracking
        self._error_history: deque = deque(maxlen=1000)
        self._error_counts: Dict[ErrorType, int] = defaultdict(int)
        
        # Recovery strategies
        self._recovery_strategies: Dict[ErrorType, List[RecoveryAction]] = {
            ErrorType.SERIAL_ERROR: [RecoveryAction.RETRY, RecoveryAction.RECONNECT, RecoveryAction.RESET],
            ErrorType.NETWORK_ERROR: [RecoveryAction.RETRY, RecoveryAction.FAILOVER],
            ErrorType.PROTOCOL_ERROR: [RecoveryAction.RESET, RecoveryAction.IGNORE],
            ErrorType.SERVICE_ERROR: [RecoveryAction.RETRY, RecoveryAction.DEGRADE],
            ErrorType.TIMEOUT_ERROR: [RecoveryAction.RETRY, RecoveryAction.RECONNECT],
            ErrorType.MEMORY_ERROR: [RecoveryAction.DEGRADE, RecoveryAction.SHUTDOWN],
            ErrorType.SYSTEM_ERROR: [RecoveryAction.RESET, RecoveryAction.SHUTDOWN]  # Changed RESTART to RESET
        }
        
        # Background tasks
        self._monitoring_tasks: List[asyncio.Task] = []
        
        logger.info("Error recovery manager initialized")
    
    def get_circuit_breaker(self, service: str) -> CircuitBreaker:
        """Get or create circuit breaker for service"""
        if service not in self._circuit_breakers:
            cb_config = self.config.get('circuit_breaker', {})
            self._circuit_breakers[service] = CircuitBreaker(
                failure_threshold=cb_config.get('failure_threshold', 5),
                recovery_timeout=cb_config.get('recovery_timeout', 60),
                half_open_max_calls=cb_config.get('half_open_max_calls', 3)
            )
        
        return self._circuit_breakers[service]
    
    async def handle_error(self, error_event: ErrorEvent) -> bool:
        """Handle an error event and attempt recovery"""
        self._error_history.append(error_event)
        self._error_counts[error_event.error_type] += 1
        
        logger.error(f"Handling error: {error_event.description}")
        
        # Get recovery strategies for this error type
        strategies = self._recovery_strategies.get(
            error_event.error_type, 
            [RecoveryAction.RETRY]
        )
        
        # Attempt recovery using each strategy
        for strategy in strategies:
            try:
                success = await self._execute_recovery_action(strategy, error_event)
                if success:
                    logger.info(f"Recovery successful using strategy: {strategy.name}")
                    return True
                    
            except Exception as e:
                logger.error(f"Recovery strategy {strategy.name} failed: {e}")
                continue
        
        logger.error(f"All recovery strategies failed for: {error_event.description}")
        return False
    
    async def _execute_recovery_action(self, action: RecoveryAction, 
                                     error_event: ErrorEvent) -> bool:
        """Execute a specific recovery action"""
        component = error_event.component
        
        if action == RecoveryAction.RETRY:
            # Retry the failed operation
            return await self._retry_operation(error_event)
            
        elif action == RecoveryAction.RECONNECT:
            # Reconnect the component
            return await self._reconnect_component(component)
            
        elif action == RecoveryAction.RESET:
            # Reset the component state
            return await self._reset_component(component)
            
        elif action == RecoveryAction.FAILOVER:
            # Failover to backup
            return await self._failover_component(component)
            
        elif action == RecoveryAction.DEGRADE:
            # Degrade service gracefully
            return await self._degrade_service(component)
            
        elif action == RecoveryAction.SHUTDOWN:
            # Shutdown component/system
            return await self._shutdown_component(component)
            
        elif action == RecoveryAction.IGNORE:
            # Ignore the error
            logger.info(f"Ignoring error in {component}")
            return True
        
        return False
    
    async def _retry_operation(self, error_event: ErrorEvent) -> bool:
        """Retry the failed operation"""
        try:
            # This would retry the specific operation that failed
            # Implementation depends on the specific operation
            await asyncio.sleep(1)  # Simple delay for retry
            return True
            
        except Exception as e:
            logger.error(f"Retry failed: {e}")
            return False
    
    async def _reconnect_component(self, component: str) -> bool:
        """Reconnect a component"""
        try:
            return await self.connection_recovery_manager.recover_connection(component)
            
        except Exception as e:
            logger.error(f"Reconnection failed for {component}: {e}")
            return False
    
    async def _reset_component(self, component: str) -> bool:
        """Reset component state"""
        try:
            # Component-specific reset logic would go here
            logger.info(f"Resetting component: {component}")
            await asyncio.sleep(0.1)  # Simulate reset time
            return True
            
        except Exception as e:
            logger.error(f"Reset failed for {component}: {e}")
            return False
    
    async def _failover_component(self, component: str) -> bool:
        """Failover to backup component"""
        try:
            return await self.connection_recovery_manager.recover_connection(component)
            
        except Exception as e:
            logger.error(f"Failover failed for {component}: {e}")
            return False
    
    async def _degrade_service(self, component: str) -> bool:
        """Gracefully degrade service"""
        try:
            logger.warning(f"Degrading service for component: {component}")
            # Implement service degradation logic
            return True
            
        except Exception as e:
            logger.error(f"Service degradation failed for {component}: {e}")
            return False
    
    async def _shutdown_component(self, component: str) -> bool:
        """Shutdown component"""
        try:
            logger.critical(f"Shutting down component: {component}")
            # Implement component shutdown logic
            return True
            
        except Exception as e:
            logger.error(f"Component shutdown failed for {component}: {e}")
            return False
    
    async def start_monitoring(self):
        """Start background monitoring tasks"""
        self._monitoring_tasks.append(
            asyncio.create_task(self._health_monitoring_loop())
        )
        self._monitoring_tasks.append(
            asyncio.create_task(self._error_analysis_loop())
        )
        
        logger.info("Error recovery monitoring started")
    
    async def stop_monitoring(self):
        """Stop monitoring tasks"""
        for task in self._monitoring_tasks:
            task.cancel()
        
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
        
        self._monitoring_tasks.clear()
        logger.info("Error recovery monitoring stopped")
    
    async def _health_monitoring_loop(self):
        """Background health monitoring"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                # Check circuit breaker states
                for service, cb in self._circuit_breakers.items():
                    if cb.state == CircuitState.OPEN:
                        logger.warning(f"Circuit breaker OPEN for service: {service}")
                
                # Check connection health
                # This would integrate with actual connections
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
    
    async def _error_analysis_loop(self):
        """Background error analysis"""
        while True:
            try:
                await asyncio.sleep(300)  # Analyze every 5 minutes
                
                # Analyze error patterns
                recent_errors = [
                    error for error in self._error_history
                    if time.time() - error.timestamp < 3600  # Last hour
                ]
                
                if len(recent_errors) > 50:  # High error rate
                    logger.warning(f"High error rate detected: {len(recent_errors)} errors in last hour")
                
                # Check for error spikes
                error_counts = defaultdict(int)
                for error in recent_errors:
                    error_counts[error.error_type] += 1
                
                for error_type, count in error_counts.items():
                    if count > 10:  # Threshold for concern
                        logger.warning(f"High frequency of {error_type.name}: {count} occurrences")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error analysis error: {e}")
    
    def get_recovery_status(self) -> Dict[str, Any]:
        """Get error recovery system status"""
        return {
            'total_errors': len(self._error_history),
            'error_counts': {k.name: v for k, v in self._error_counts.items()},
            'circuit_breakers': {
                service: cb.get_stats()
                for service, cb in self._circuit_breakers.items()
            },
            'active_recovery_tasks': len(self.connection_recovery_manager._recovery_tasks),
            'monitoring_active': len(self._monitoring_tasks) > 0
        }
    
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get error summary for specified time period"""
        cutoff_time = time.time() - (hours * 3600)
        recent_errors = [
            error for error in self._error_history
            if error.timestamp > cutoff_time
        ]
        
        error_types = defaultdict(int)
        components = defaultdict(int)
        
        for error in recent_errors:
            error_types[error.error_type.name] += 1
            components[error.component] += 1
        
        return {
            'time_period_hours': hours,
            'total_errors': len(recent_errors),
            'error_types': dict(error_types),
            'affected_components': dict(components),
            'error_rate_per_hour': len(recent_errors) / hours if hours > 0 else 0
        }