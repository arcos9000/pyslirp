#!/usr/bin/env python3
"""
Connection Pool and Performance Optimizations for PyLiRP
Provides efficient connection management, caching, and performance enhancements
"""

import asyncio
import time
import weakref
from collections import defaultdict, deque, OrderedDict
from typing import Dict, Optional, Tuple, Any, Set, List
from dataclasses import dataclass, field
from enum import Enum, auto
import statistics

from safe_logger import get_safe_logger

logger = get_safe_logger(__name__)

class ConnectionState(Enum):
    """Connection state for pooling"""
    IDLE = auto()
    ACTIVE = auto()
    CLOSING = auto()
    CLOSED = auto()

@dataclass
class PooledConnection:
    """Represents a pooled connection with metadata"""
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    host: str
    port: int
    created_at: float
    last_used: float
    use_count: int = 0
    state: ConnectionState = ConnectionState.IDLE
    service_name: str = ""
    
    def __post_init__(self):
        self.last_used = time.time()
    
    @property
    def age(self) -> float:
        """Age of connection in seconds"""
        return time.time() - self.created_at
    
    @property
    def idle_time(self) -> float:
        """Time since last use in seconds"""
        return time.time() - self.last_used
    
    def mark_used(self):
        """Mark connection as recently used"""
        self.last_used = time.time()
        self.use_count += 1
        self.state = ConnectionState.ACTIVE
    
    def mark_idle(self):
        """Mark connection as idle"""
        self.state = ConnectionState.IDLE
    
    async def is_alive(self) -> bool:
        """Check if connection is still alive"""
        if self.writer.is_closing():
            return False
        
        try:
            # Try to write a small amount of data to test connection
            self.writer.write(b'')
            await asyncio.wait_for(self.writer.drain(), timeout=0.1)
            return True
        except:
            return False

@dataclass
class PoolStats:
    """Connection pool statistics"""
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    connections_created: int = 0
    connections_closed: int = 0
    connections_reused: int = 0
    average_connection_age: float = 0.0
    
    def hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

class LRUCache:
    """Least Recently Used cache implementation"""
    
    def __init__(self, max_size: int):
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()
    
    def get(self, key: Any) -> Optional[Any]:
        """Get item from cache, marking it as recently used"""
        if key in self._cache:
            value = self._cache.pop(key)
            self._cache[key] = value  # Move to end (most recent)
            return value
        return None
    
    def put(self, key: Any, value: Any):
        """Put item in cache, evicting LRU if necessary"""
        if key in self._cache:
            self._cache.pop(key)
        elif len(self._cache) >= self.max_size:
            # Remove least recently used (first item)
            self._cache.popitem(last=False)
        
        self._cache[key] = value
    
    def remove(self, key: Any) -> bool:
        """Remove item from cache"""
        if key in self._cache:
            self._cache.pop(key)
            return True
        return False
    
    def clear(self):
        """Clear all cached items"""
        self._cache.clear()
    
    def size(self) -> int:
        """Get current cache size"""
        return len(self._cache)

class ConnectionPool:
    """Efficient connection pool with LRU caching and health monitoring"""
    
    def __init__(self, max_connections: int = 100, 
                 idle_timeout: int = 300,
                 max_connection_age: int = 3600,
                 health_check_interval: int = 60):
        self.max_connections = max_connections
        self.idle_timeout = idle_timeout
        self.max_connection_age = max_connection_age
        self.health_check_interval = health_check_interval
        
        # Connection storage by service key (host, port)
        self._connections: Dict[Tuple[str, int], List[PooledConnection]] = defaultdict(list)
        self._cache = LRUCache(max_connections)
        self._stats = PoolStats()
        
        # Active connections tracking
        self._active_connections: Set[PooledConnection] = set()
        
        # Connection limits per service
        self._per_service_limits: Dict[Tuple[str, int], int] = {}
        
        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None
        self._start_health_checks()
        
        # Metrics tracking
        self._connection_times: deque = deque(maxlen=1000)
        self._response_times: Dict[Tuple[str, int], deque] = defaultdict(
            lambda: deque(maxlen=100)
        )
    
    def set_service_limit(self, host: str, port: int, limit: int):
        """Set connection limit for a specific service"""
        self._per_service_limits[(host, port)] = limit
    
    async def get_connection(self, host: str, port: int, 
                           service_name: str = "") -> Optional[PooledConnection]:
        """
        Get or create a connection to the specified service
        
        Args:
            host: Target host
            port: Target port  
            service_name: Service name for logging/metrics
            
        Returns:
            PooledConnection if successful, None if failed
        """
        service_key = (host, port)
        start_time = time.time()
        
        # Try to get cached connection first
        cached_conn = self._get_cached_connection(service_key)
        if cached_conn:
            if await cached_conn.is_alive():
                cached_conn.mark_used()
                cached_conn.service_name = service_name
                self._active_connections.add(cached_conn)
                self._stats.cache_hits += 1
                self._stats.connections_reused += 1
                
                logger.debug(f"Reusing cached connection to {host}:{port}")
                return cached_conn
            else:
                # Remove dead connection
                await self._remove_connection(cached_conn, service_key)
        
        self._stats.cache_misses += 1
        
        # Check connection limits
        if not self._can_create_connection(service_key):
            logger.warning(f"Connection limit exceeded for {host}:{port}")
            return None
        
        # Create new connection
        try:
            logger.debug(f"Creating new connection to {host}:{port}")
            reader, writer = await asyncio.open_connection(host, port)
            
            connection = PooledConnection(
                reader=reader,
                writer=writer,
                host=host,
                port=port,
                created_at=time.time(),
                last_used=time.time(),
                service_name=service_name
            )
            
            connection.mark_used()
            self._active_connections.add(connection)
            self._connections[service_key].append(connection)
            
            # Update statistics
            self._stats.connections_created += 1
            self._stats.total_connections += 1
            
            # Track connection creation time
            connection_time = time.time() - start_time
            self._connection_times.append(connection_time)
            
            logger.info(f"Created new connection to {host}:{port} in {connection_time:.3f}s")
            return connection
            
        except Exception as e:
            logger.error(f"Failed to create connection to {host}:{port}: {e}")
            return None
    
    def _get_cached_connection(self, service_key: Tuple[str, int]) -> Optional[PooledConnection]:
        """Get cached connection for service"""
        # Try cache first
        cached = self._cache.get(service_key)
        if cached and isinstance(cached, PooledConnection):
            return cached
        
        # Try idle connections for this service
        connections = self._connections.get(service_key, [])
        for conn in connections:
            if conn.state == ConnectionState.IDLE:
                return conn
        
        return None
    
    def _can_create_connection(self, service_key: Tuple[str, int]) -> bool:
        """Check if we can create a new connection"""
        # Check global limit
        if self._stats.total_connections >= self.max_connections:
            return False
        
        # Check per-service limit
        service_limit = self._per_service_limits.get(service_key)
        if service_limit is not None:
            service_connections = len(self._connections.get(service_key, []))
            if service_connections >= service_limit:
                return False
        
        return True
    
    async def return_connection(self, connection: PooledConnection):
        """Return a connection to the pool"""
        if connection not in self._active_connections:
            logger.warning("Attempting to return unknown connection")
            return
        
        self._active_connections.discard(connection)
        
        # Check if connection is still alive
        if await connection.is_alive():
            connection.mark_idle()
            service_key = (connection.host, connection.port)
            self._cache.put(service_key, connection)
            logger.debug(f"Returned connection to pool: {connection.host}:{connection.port}")
        else:
            # Connection is dead, remove it
            await self._remove_connection(connection, (connection.host, connection.port))
    
    async def close_connection(self, connection: PooledConnection):
        """Close and remove a connection from the pool"""
        service_key = (connection.host, connection.port)
        await self._remove_connection(connection, service_key)
    
    async def _remove_connection(self, connection: PooledConnection, 
                               service_key: Tuple[str, int]):
        """Remove connection from all tracking structures"""
        self._active_connections.discard(connection)
        
        # Remove from connections list
        if service_key in self._connections:
            try:
                self._connections[service_key].remove(connection)
                if not self._connections[service_key]:
                    del self._connections[service_key]
            except ValueError:
                pass  # Connection not in list
        
        # Remove from cache
        self._cache.remove(service_key)
        
        # Close the connection
        if not connection.writer.is_closing():
            connection.writer.close()
            try:
                await connection.writer.wait_closed()
            except:
                pass  # Ignore cleanup errors
        
        # Update statistics
        self._stats.connections_closed += 1
        self._stats.total_connections = max(0, self._stats.total_connections - 1)
        
        logger.debug(f"Removed connection: {connection.host}:{connection.port}")
    
    def _start_health_checks(self):
        """Start background health check task"""
        async def health_check_loop():
            while True:
                try:
                    await self._perform_health_checks()
                    await asyncio.sleep(self.health_check_interval)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Health check error: {e}")
                    await asyncio.sleep(5)  # Retry after short delay
        
        self._health_check_task = asyncio.create_task(health_check_loop())
    
    async def _perform_health_checks(self):
        """Perform health checks and cleanup"""
        current_time = time.time()
        connections_to_remove = []
        
        # Check all connections
        for service_key, connections in self._connections.items():
            for conn in connections[:]:  # Create copy to avoid modification during iteration
                should_remove = False
                
                # Check idle timeout
                if (conn.state == ConnectionState.IDLE and 
                    conn.idle_time > self.idle_timeout):
                    should_remove = True
                    logger.debug(f"Connection idle timeout: {service_key}")
                
                # Check max age
                elif conn.age > self.max_connection_age:
                    should_remove = True
                    logger.debug(f"Connection age timeout: {service_key}")
                
                # Check if connection is alive
                elif not await conn.is_alive():
                    should_remove = True
                    logger.debug(f"Connection health check failed: {service_key}")
                
                if should_remove:
                    connections_to_remove.append((conn, service_key))
        
        # Remove unhealthy connections
        for conn, service_key in connections_to_remove:
            await self._remove_connection(conn, service_key)
        
        # Update statistics
        self._update_stats()
        
        if connections_to_remove:
            logger.info(f"Health check completed, removed {len(connections_to_remove)} connections")
    
    def _update_stats(self):
        """Update pool statistics"""
        total_connections = sum(len(conns) for conns in self._connections.values())
        active_connections = len(self._active_connections)
        idle_connections = total_connections - active_connections
        
        self._stats.total_connections = total_connections
        self._stats.active_connections = active_connections
        self._stats.idle_connections = idle_connections
        
        # Calculate average connection age
        if total_connections > 0:
            ages = []
            for connections in self._connections.values():
                ages.extend(conn.age for conn in connections)
            self._stats.average_connection_age = statistics.mean(ages)
    
    def get_stats(self) -> PoolStats:
        """Get current pool statistics"""
        self._update_stats()
        return self._stats
    
    def get_connection_metrics(self) -> Dict[str, Any]:
        """Get detailed connection metrics"""
        metrics = {
            'total_connections': self._stats.total_connections,
            'active_connections': self._stats.active_connections,
            'idle_connections': self._stats.idle_connections,
            'cache_hit_rate': self._stats.hit_rate(),
            'connections_per_service': {
                f"{host}:{port}": len(conns) 
                for (host, port), conns in self._connections.items()
            },
            'average_connection_time': 0.0,
            'average_response_times': {}
        }
        
        # Calculate average connection time
        if self._connection_times:
            metrics['average_connection_time'] = statistics.mean(self._connection_times)
        
        # Calculate average response times per service
        for service_key, times in self._response_times.items():
            if times:
                host, port = service_key
                metrics['average_response_times'][f"{host}:{port}"] = statistics.mean(times)
        
        return metrics
    
    def record_response_time(self, host: str, port: int, response_time: float):
        """Record response time for a service"""
        service_key = (host, port)
        self._response_times[service_key].append(response_time)
    
    async def warmup_connections(self, services: List[Tuple[str, int, str]], 
                               connections_per_service: int = 2):
        """
        Pre-create connections for frequently used services
        
        Args:
            services: List of (host, port, service_name) tuples
            connections_per_service: Number of connections to create per service
        """
        logger.info(f"Warming up connection pool for {len(services)} services")
        
        warmup_tasks = []
        for host, port, service_name in services:
            for _ in range(connections_per_service):
                task = asyncio.create_task(
                    self._create_warmup_connection(host, port, service_name)
                )
                warmup_tasks.append(task)
        
        # Wait for all warmup connections
        results = await asyncio.gather(*warmup_tasks, return_exceptions=True)
        
        successful = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(f"Warmup completed: {successful}/{len(warmup_tasks)} connections created")
    
    async def _create_warmup_connection(self, host: str, port: int, service_name: str):
        """Create a single warmup connection"""
        try:
            conn = await self.get_connection(host, port, service_name)
            if conn:
                await self.return_connection(conn)
                logger.debug(f"Warmed up connection to {host}:{port}")
        except Exception as e:
            logger.warning(f"Failed to warm up connection to {host}:{port}: {e}")
    
    async def shutdown(self):
        """Shutdown the connection pool and close all connections"""
        logger.info("Shutting down connection pool")
        
        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        all_connections = []
        for connections in self._connections.values():
            all_connections.extend(connections)
        all_connections.extend(self._active_connections)
        
        close_tasks = []
        for conn in all_connections:
            if not conn.writer.is_closing():
                conn.writer.close()
                close_tasks.append(conn.writer.wait_closed())
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # Clear all data structures
        self._connections.clear()
        self._cache.clear()
        self._active_connections.clear()
        
        logger.info("Connection pool shutdown complete")

class PerformanceMonitor:
    """Performance monitoring and optimization"""
    
    def __init__(self, sample_size: int = 1000):
        self.sample_size = sample_size
        
        # Performance metrics
        self._cpu_times: deque = deque(maxlen=sample_size)
        self._memory_usage: deque = deque(maxlen=sample_size)
        self._packet_processing_times: deque = deque(maxlen=sample_size)
        self._throughput_samples: deque = deque(maxlen=sample_size)
        
        # Connection metrics
        self._connection_latencies: deque = deque(maxlen=sample_size)
        self._error_rates: deque = deque(maxlen=sample_size)
        
        # Buffer management
        self._buffer_pool = asyncio.Queue(maxsize=100)
        self._initialize_buffer_pool()
    
    def _initialize_buffer_pool(self):
        """Pre-allocate buffers for zero-copy operations"""
        for _ in range(50):  # Start with 50 buffers
            buffer = bytearray(8192)  # 8KB buffers
            self._buffer_pool.put_nowait(buffer)
    
    async def get_buffer(self, size: int = 8192) -> bytearray:
        """Get a buffer from the pool or create new one"""
        try:
            buffer = self._buffer_pool.get_nowait()
            if len(buffer) >= size:
                return buffer
        except asyncio.QueueEmpty:
            pass
        
        # Create new buffer if pool is empty or buffer too small
        return bytearray(size)
    
    async def return_buffer(self, buffer: bytearray):
        """Return a buffer to the pool"""
        try:
            # Clear the buffer and return to pool
            buffer[:] = b'\x00' * len(buffer)
            self._buffer_pool.put_nowait(buffer)
        except asyncio.QueueFull:
            pass  # Pool is full, let garbage collector handle it
    
    def record_packet_processing_time(self, processing_time: float):
        """Record packet processing time"""
        self._packet_processing_times.append(processing_time)
    
    def record_connection_latency(self, latency: float):
        """Record connection establishment latency"""
        self._connection_latencies.append(latency)
    
    def record_throughput(self, bytes_per_second: float):
        """Record throughput measurement"""
        self._throughput_samples.append(bytes_per_second)
    
    def record_error_rate(self, error_rate: float):
        """Record error rate (0.0 to 1.0)"""
        self._error_rates.append(error_rate)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        metrics = {}
        
        # Packet processing performance
        if self._packet_processing_times:
            metrics['avg_packet_processing_time'] = statistics.mean(
                self._packet_processing_times
            )
            metrics['p95_packet_processing_time'] = self._percentile(
                self._packet_processing_times, 95
            )
        
        # Connection performance
        if self._connection_latencies:
            metrics['avg_connection_latency'] = statistics.mean(
                self._connection_latencies
            )
            metrics['p95_connection_latency'] = self._percentile(
                self._connection_latencies, 95
            )
        
        # Throughput
        if self._throughput_samples:
            metrics['avg_throughput_bps'] = statistics.mean(self._throughput_samples)
            metrics['max_throughput_bps'] = max(self._throughput_samples)
        
        # Error rates
        if self._error_rates:
            metrics['avg_error_rate'] = statistics.mean(self._error_rates)
            metrics['max_error_rate'] = max(self._error_rates)
        
        # Buffer pool status
        metrics['buffer_pool_size'] = self._buffer_pool.qsize()
        
        return metrics
    
    def _percentile(self, data: deque, percentile: float) -> float:
        """Calculate percentile of data"""
        if not data:
            return 0.0
        
        sorted_data = sorted(data)
        index = int(len(sorted_data) * (percentile / 100.0))
        index = min(index, len(sorted_data) - 1)
        return sorted_data[index]
    
    def optimize_buffers(self) -> Dict[str, Any]:
        """Analyze and suggest buffer optimizations"""
        recommendations = {}
        
        if self._packet_processing_times:
            avg_time = statistics.mean(self._packet_processing_times)
            
            if avg_time > 0.001:  # 1ms
                recommendations['buffer_optimization'] = (
                    "Consider increasing buffer sizes for better performance"
                )
            elif avg_time < 0.0001:  # 0.1ms  
                recommendations['buffer_optimization'] = (
                    "Buffer sizes appear optimal"
                )
        
        # Buffer pool recommendations
        current_pool_size = self._buffer_pool.qsize()
        if current_pool_size < 10:
            recommendations['buffer_pool'] = (
                "Consider increasing buffer pool size"
            )
        
        return recommendations