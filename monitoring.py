#!/usr/bin/env python3
"""
Monitoring and Observability Framework for PyLiRP
Provides comprehensive metrics collection, health monitoring, and observability
"""

import asyncio
import time
import json
import struct
import threading
from collections import defaultdict, deque
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
import logging
from datetime import datetime, timedelta
from pathlib import Path
import statistics

logger = logging.getLogger(__name__)

class MetricType(Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"

class HealthStatus(Enum):
    """Health check status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

@dataclass
class Metric:
    """Base metric class"""
    name: str
    metric_type: MetricType
    description: str
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

@dataclass
class Counter(Metric):
    """Counter metric (monotonically increasing)"""
    value: int = 0
    metric_type: MetricType = field(default=MetricType.COUNTER, init=False)
    
    def inc(self, amount: int = 1):
        """Increment counter"""
        self.value += amount
        self.timestamp = time.time()
    
    def reset(self):
        """Reset counter to zero"""
        self.value = 0
        self.timestamp = time.time()

@dataclass
class Gauge(Metric):
    """Gauge metric (can increase or decrease)"""
    value: float = 0.0
    metric_type: MetricType = field(default=MetricType.GAUGE, init=False)
    
    def set(self, value: float):
        """Set gauge value"""
        self.value = value
        self.timestamp = time.time()
    
    def inc(self, amount: float = 1.0):
        """Increment gauge"""
        self.value += amount
        self.timestamp = time.time()
    
    def dec(self, amount: float = 1.0):
        """Decrement gauge"""
        self.value -= amount
        self.timestamp = time.time()

@dataclass
class HistogramBucket:
    """Histogram bucket"""
    upper_bound: float
    count: int = 0

@dataclass
class Histogram(Metric):
    """Histogram metric for measuring distributions"""
    buckets: List[HistogramBucket] = field(default_factory=list)
    count: int = 0
    sum: float = 0.0
    metric_type: MetricType = field(default=MetricType.HISTOGRAM, init=False)
    
    def __post_init__(self):
        if not self.buckets:
            # Default buckets for latency measurements (milliseconds)
            bounds = [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, float('inf')]
            self.buckets = [HistogramBucket(bound) for bound in bounds]
    
    def observe(self, value: float):
        """Observe a value"""
        self.count += 1
        self.sum += value
        self.timestamp = time.time()
        
        # Update buckets
        for bucket in self.buckets:
            if value <= bucket.upper_bound:
                bucket.count += 1

@dataclass
class Summary(Metric):
    """Summary metric with quantiles"""
    samples: deque = field(default_factory=lambda: deque(maxlen=1000))
    count: int = 0
    sum: float = 0.0
    metric_type: MetricType = field(default=MetricType.SUMMARY, init=False)
    
    def observe(self, value: float):
        """Observe a value"""
        self.samples.append(value)
        self.count += 1
        self.sum += value
        self.timestamp = time.time()
    
    def quantile(self, q: float) -> float:
        """Calculate quantile (0.0 to 1.0)"""
        if not self.samples:
            return 0.0
        
        sorted_samples = sorted(self.samples)
        index = int(len(sorted_samples) * q)
        return sorted_samples[min(index, len(sorted_samples) - 1)]

class MetricsCollector:
    """Comprehensive metrics collection system"""
    
    def __init__(self):
        self._metrics: Dict[str, Metric] = {}
        self._lock = threading.Lock()
        
        # Pre-defined metrics
        self._initialize_core_metrics()
    
    def _initialize_core_metrics(self):
        """Initialize core system metrics"""
        # Connection metrics
        self._metrics['connections_total'] = Counter(
            'connections_total', MetricType.COUNTER,
            'Total number of connections established'
        )
        self._metrics['connections_active'] = Gauge(
            'connections_active', MetricType.GAUGE,
            'Number of currently active connections'
        )
        self._metrics['connections_failed'] = Counter(
            'connections_failed', MetricType.COUNTER,
            'Total number of failed connection attempts'
        )
        
        # Data transfer metrics
        self._metrics['bytes_sent_total'] = Counter(
            'bytes_sent_total', MetricType.COUNTER,
            'Total bytes sent'
        )
        self._metrics['bytes_received_total'] = Counter(
            'bytes_received_total', MetricType.COUNTER,
            'Total bytes received'
        )
        self._metrics['packets_processed_total'] = Counter(
            'packets_processed_total', MetricType.COUNTER,
            'Total packets processed'
        )
        
        # Performance metrics
        self._metrics['packet_processing_duration'] = Histogram(
            'packet_processing_duration', MetricType.HISTOGRAM,
            'Time spent processing packets in milliseconds'
        )
        self._metrics['connection_duration'] = Histogram(
            'connection_duration', MetricType.HISTOGRAM,
            'Connection establishment time in milliseconds'
        )
        
        # PPP metrics
        self._metrics['ppp_frames_sent'] = Counter(
            'ppp_frames_sent', MetricType.COUNTER,
            'Total PPP frames sent'
        )
        self._metrics['ppp_frames_received'] = Counter(
            'ppp_frames_received', MetricType.COUNTER,
            'Total PPP frames received'
        )
        self._metrics['ppp_errors_total'] = Counter(
            'ppp_errors_total', MetricType.COUNTER,
            'Total PPP protocol errors'
        )
        
        # TCP metrics
        self._metrics['tcp_segments_sent'] = Counter(
            'tcp_segments_sent', MetricType.COUNTER,
            'Total TCP segments sent'
        )
        self._metrics['tcp_segments_received'] = Counter(
            'tcp_segments_received', MetricType.COUNTER,
            'Total TCP segments received'
        )
        self._metrics['tcp_retransmissions'] = Counter(
            'tcp_retransmissions', MetricType.COUNTER,
            'Total TCP retransmissions'
        )
        
        # Security metrics
        self._metrics['security_events_total'] = Counter(
            'security_events_total', MetricType.COUNTER,
            'Total security events'
        )
        self._metrics['blocked_connections'] = Counter(
            'blocked_connections', MetricType.COUNTER,
            'Total blocked connection attempts'
        )
        
        # Service metrics
        self._metrics['service_response_time'] = Histogram(
            'service_response_time', MetricType.HISTOGRAM,
            'Service response time in milliseconds'
        )
        self._metrics['service_errors_total'] = Counter(
            'service_errors_total', MetricType.COUNTER,
            'Total service errors'
        )
    
    def counter(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None) -> Counter:
        """Get or create a counter metric"""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Counter(name, MetricType.COUNTER, description, labels or {})
            return self._metrics[name]
    
    def gauge(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None) -> Gauge:
        """Get or create a gauge metric"""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Gauge(name, MetricType.GAUGE, description, labels or {})
            return self._metrics[name]
    
    def histogram(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None) -> Histogram:
        """Get or create a histogram metric"""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Histogram(name, MetricType.HISTOGRAM, description, labels or {})
            return self._metrics[name]
    
    def summary(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None) -> Summary:
        """Get or create a summary metric"""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = Summary(name, MetricType.SUMMARY, description, labels or {})
            return self._metrics[name]
    
    def get_all_metrics(self) -> Dict[str, Metric]:
        """Get all metrics"""
        with self._lock:
            return self._metrics.copy()
    
    def reset_metrics(self):
        """Reset all metrics"""
        with self._lock:
            for metric in self._metrics.values():
                if isinstance(metric, Counter):
                    metric.reset()
                elif isinstance(metric, Gauge):
                    metric.set(0.0)
                elif isinstance(metric, Histogram):
                    metric.buckets = [HistogramBucket(b.upper_bound) for b in metric.buckets]
                    metric.count = 0
                    metric.sum = 0.0
                elif isinstance(metric, Summary):
                    metric.samples.clear()
                    metric.count = 0
                    metric.sum = 0.0

class HealthChecker:
    """System health monitoring"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self._health_checks: Dict[str, Callable] = {}
        self._health_status: Dict[str, HealthStatus] = {}
        self._health_details: Dict[str, str] = {}
        self._last_check_time: Dict[str, float] = {}
        
        # Register default health checks
        self._register_default_checks()
    
    def _register_default_checks(self):
        """Register default health checks"""
        self.register_check("metrics", self._check_metrics_health)
        self.register_check("connections", self._check_connections_health)
        self.register_check("performance", self._check_performance_health)
    
    def register_check(self, name: str, check_func: Callable[[], Tuple[HealthStatus, str]]):
        """Register a health check"""
        self._health_checks[name] = check_func
        self._health_status[name] = HealthStatus.UNKNOWN
        self._health_details[name] = "Not checked yet"
    
    async def run_health_checks(self) -> Dict[str, Dict[str, Any]]:
        """Run all health checks"""
        results = {}
        
        for name, check_func in self._health_checks.items():
            try:
                status, details = await asyncio.get_event_loop().run_in_executor(
                    None, check_func
                )
                self._health_status[name] = status
                self._health_details[name] = details
                self._last_check_time[name] = time.time()
                
                results[name] = {
                    'status': status.value,
                    'details': details,
                    'last_check': self._last_check_time[name]
                }
                
            except Exception as e:
                self._health_status[name] = HealthStatus.UNHEALTHY
                self._health_details[name] = f"Health check failed: {e}"
                self._last_check_time[name] = time.time()
                
                results[name] = {
                    'status': HealthStatus.UNHEALTHY.value,
                    'details': self._health_details[name],
                    'last_check': self._last_check_time[name]
                }
                
                logger.error(f"Health check '{name}' failed: {e}")
        
        return results
    
    def get_overall_health(self) -> HealthStatus:
        """Get overall system health status"""
        if not self._health_status:
            return HealthStatus.UNKNOWN
        
        statuses = list(self._health_status.values())
        
        if any(status == HealthStatus.UNHEALTHY for status in statuses):
            return HealthStatus.UNHEALTHY
        elif any(status == HealthStatus.DEGRADED for status in statuses):
            return HealthStatus.DEGRADED
        elif all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN
    
    def _check_metrics_health(self) -> Tuple[HealthStatus, str]:
        """Check metrics system health"""
        metrics = self.metrics_collector.get_all_metrics()
        
        if not metrics:
            return HealthStatus.UNHEALTHY, "No metrics available"
        
        # Check for recent activity
        recent_activity = False
        current_time = time.time()
        
        for metric in metrics.values():
            if current_time - metric.timestamp < 300:  # Active within 5 minutes
                recent_activity = True
                break
        
        if not recent_activity:
            return HealthStatus.DEGRADED, "No recent metric activity"
        
        return HealthStatus.HEALTHY, f"{len(metrics)} metrics active"
    
    def _check_connections_health(self) -> Tuple[HealthStatus, str]:
        """Check connection health"""
        metrics = self.metrics_collector.get_all_metrics()
        
        active_connections = metrics.get('connections_active')
        failed_connections = metrics.get('connections_failed')
        
        if not active_connections or not failed_connections:
            return HealthStatus.UNKNOWN, "Connection metrics not available"
        
        # Check failure rate
        total_attempts = active_connections.value + failed_connections.value
        if total_attempts > 0:
            failure_rate = failed_connections.value / total_attempts
            if failure_rate > 0.5:
                return HealthStatus.UNHEALTHY, f"High failure rate: {failure_rate:.2%}"
            elif failure_rate > 0.1:
                return HealthStatus.DEGRADED, f"Elevated failure rate: {failure_rate:.2%}"
        
        return HealthStatus.HEALTHY, f"{active_connections.value} active connections"
    
    def _check_performance_health(self) -> Tuple[HealthStatus, str]:
        """Check performance health"""
        metrics = self.metrics_collector.get_all_metrics()
        
        packet_duration = metrics.get('packet_processing_duration')
        
        if not packet_duration or not isinstance(packet_duration, Histogram):
            return HealthStatus.UNKNOWN, "Performance metrics not available"
        
        if packet_duration.count == 0:
            return HealthStatus.UNKNOWN, "No performance data yet"
        
        # Calculate average processing time
        avg_time = packet_duration.sum / packet_duration.count
        
        if avg_time > 10.0:  # 10ms
            return HealthStatus.UNHEALTHY, f"High processing time: {avg_time:.2f}ms"
        elif avg_time > 5.0:  # 5ms
            return HealthStatus.DEGRADED, f"Elevated processing time: {avg_time:.2f}ms"
        
        return HealthStatus.HEALTHY, f"Average processing time: {avg_time:.2f}ms"

class PrometheusExporter:
    """Prometheus metrics exporter"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
    
    def generate_prometheus_format(self) -> str:
        """Generate metrics in Prometheus format"""
        lines = []
        metrics = self.metrics_collector.get_all_metrics()
        
        for name, metric in metrics.items():
            # Add help and type comments
            lines.append(f"# HELP {name} {metric.description}")
            lines.append(f"# TYPE {name} {metric.metric_type.value}")
            
            if isinstance(metric, Counter):
                labels_str = self._format_labels(metric.labels)
                lines.append(f"{name}{labels_str} {metric.value}")
                
            elif isinstance(metric, Gauge):
                labels_str = self._format_labels(metric.labels)
                lines.append(f"{name}{labels_str} {metric.value}")
                
            elif isinstance(metric, Histogram):
                # Histogram buckets
                for bucket in metric.buckets:
                    bucket_labels = {**metric.labels, 'le': str(bucket.upper_bound)}
                    labels_str = self._format_labels(bucket_labels)
                    lines.append(f"{name}_bucket{labels_str} {bucket.count}")
                
                # Histogram sum and count
                labels_str = self._format_labels(metric.labels)
                lines.append(f"{name}_sum{labels_str} {metric.sum}")
                lines.append(f"{name}_count{labels_str} {metric.count}")
                
            elif isinstance(metric, Summary):
                # Summary quantiles
                for q in [0.5, 0.9, 0.95, 0.99]:
                    quantile_labels = {**metric.labels, 'quantile': str(q)}
                    labels_str = self._format_labels(quantile_labels)
                    value = metric.quantile(q)
                    lines.append(f"{name}{labels_str} {value}")
                
                # Summary sum and count
                labels_str = self._format_labels(metric.labels)
                lines.append(f"{name}_sum{labels_str} {metric.sum}")
                lines.append(f"{name}_count{labels_str} {metric.count}")
            
            lines.append("")  # Empty line between metrics
        
        return "\n".join(lines)
    
    def _format_labels(self, labels: Dict[str, str]) -> str:
        """Format labels for Prometheus format"""
        if not labels:
            return ""
        
        label_pairs = [f'{key}="{value}"' for key, value in labels.items()]
        return "{" + ",".join(label_pairs) + "}"

class PacketCapture:
    """Network packet capture for debugging"""
    
    def __init__(self, max_packets: int = 10000):
        self.max_packets = max_packets
        self._packets: deque = deque(maxlen=max_packets)
        self._enabled = False
        self._pcap_file: Optional[str] = None
    
    def enable(self, pcap_file: Optional[str] = None):
        """Enable packet capture"""
        self._enabled = True
        self._pcap_file = pcap_file
        logger.info(f"Packet capture enabled, file: {pcap_file or 'memory only'}")
    
    def disable(self):
        """Disable packet capture"""
        self._enabled = False
        logger.info("Packet capture disabled")
    
    def capture_packet(self, packet_data: bytes, direction: str = "unknown", 
                      protocol: str = "unknown"):
        """Capture a packet"""
        if not self._enabled:
            return
        
        packet_info = {
            'timestamp': time.time(),
            'direction': direction,  # 'inbound' or 'outbound'
            'protocol': protocol,    # 'ppp', 'ip', 'tcp', etc.
            'size': len(packet_data),
            'data': packet_data.hex() if len(packet_data) <= 1500 else packet_data[:1500].hex()
        }
        
        self._packets.append(packet_info)
        
        # Write to pcap file if configured
        if self._pcap_file:
            self._write_pcap_packet(packet_info, packet_data)
    
    def _write_pcap_packet(self, packet_info: Dict[str, Any], packet_data: bytes):
        """Write packet to PCAP file (simplified format)"""
        # This is a simplified implementation
        # For production, consider using a proper PCAP library
        try:
            # Ensure directory exists
            pcap_path = Path(self._pcap_file)
            pcap_path.parent.mkdir(parents=True, exist_ok=True)
            
            timestamp = int(packet_info['timestamp'])
            with open(self._pcap_file, 'ab') as f:
                # Simple packet record: timestamp (4 bytes) + size (2 bytes) + data
                header = struct.pack('!IH', timestamp, len(packet_data))
                f.write(header + packet_data)
        except Exception as e:
            logger.error(f"Failed to write packet to PCAP file: {e}")
    
    def get_packets(self, count: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get captured packets"""
        if count is None:
            return list(self._packets)
        else:
            return list(self._packets)[-count:]
    
    def clear_packets(self):
        """Clear captured packets"""
        self._packets.clear()
        logger.info("Packet capture buffer cleared")

class MetricsHttpServer:
    """HTTP server for metrics endpoint"""
    
    def __init__(self, metrics_collector: MetricsCollector, 
                 health_checker: HealthChecker,
                 port: int = 9090):
        self.metrics_collector = metrics_collector
        self.health_checker = health_checker
        self.port = port
        self.prometheus_exporter = PrometheusExporter(metrics_collector)
        self._server = None
        self._app = None
    
    async def start_server(self):
        """Start HTTP server for metrics"""
        try:
            from aiohttp import web, web_request
            
            app = web.Application()
            app.router.add_get('/metrics', self._metrics_handler)
            app.router.add_get('/health', self._health_handler)
            app.router.add_get('/status', self._status_handler)
            
            runner = web.AppRunner(app)
            await runner.setup()
            
            site = web.TCPSite(runner, '0.0.0.0', self.port)
            await site.start()
            
            self._server = runner
            logger.info(f"Metrics server started on port {self.port}")
            
        except ImportError:
            logger.warning("aiohttp not available, metrics HTTP server disabled")
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")
    
    async def stop_server(self):
        """Stop HTTP server"""
        if self._server:
            await self._server.cleanup()
            self._server = None
            logger.info("Metrics server stopped")
    
    async def _metrics_handler(self, request):
        """Handle /metrics endpoint"""
        try:
            from aiohttp import web
            
            prometheus_output = self.prometheus_exporter.generate_prometheus_format()
            return web.Response(text=prometheus_output, content_type='text/plain')
            
        except Exception as e:
            return web.Response(text=f"Error generating metrics: {e}", status=500)
    
    async def _health_handler(self, request):
        """Handle /health endpoint"""
        try:
            from aiohttp import web
            
            health_results = await self.health_checker.run_health_checks()
            overall_status = self.health_checker.get_overall_health()
            
            response_data = {
                'status': overall_status.value,
                'checks': health_results,
                'timestamp': time.time()
            }
            
            status_code = 200 if overall_status == HealthStatus.HEALTHY else 503
            
            return web.json_response(response_data, status=status_code)
            
        except Exception as e:
            return web.Response(text=f"Error checking health: {e}", status=500)
    
    async def _status_handler(self, request):
        """Handle /status endpoint"""
        try:
            from aiohttp import web
            
            metrics = self.metrics_collector.get_all_metrics()
            
            # Generate summary statistics
            status_data = {
                'timestamp': time.time(),
                'uptime': time.time() - self._get_start_time(),
                'metrics_count': len(metrics),
                'connections': {
                    'active': metrics.get('connections_active', Gauge('', MetricType.GAUGE, '')).value,
                    'total': metrics.get('connections_total', Counter('', MetricType.COUNTER, '')).value,
                    'failed': metrics.get('connections_failed', Counter('', MetricType.COUNTER, '')).value
                },
                'data_transfer': {
                    'bytes_sent': metrics.get('bytes_sent_total', Counter('', MetricType.COUNTER, '')).value,
                    'bytes_received': metrics.get('bytes_received_total', Counter('', MetricType.COUNTER, '')).value,
                    'packets_processed': metrics.get('packets_processed_total', Counter('', MetricType.COUNTER, '')).value
                }
            }
            
            return web.json_response(status_data)
            
        except Exception as e:
            return web.Response(text=f"Error getting status: {e}", status=500)
    
    def _get_start_time(self) -> float:
        """Get application start time"""
        # This would typically be set when the application starts
        return getattr(self, '_start_time', time.time())

class MonitoringManager:
    """Main monitoring manager coordinating all monitoring components"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Initialize components
        self.metrics_collector = MetricsCollector()
        self.health_checker = HealthChecker(self.metrics_collector)
        self.packet_capture = PacketCapture(
            max_packets=config.get('packet_capture', {}).get('max_packets', 10000)
        )
        
        # HTTP server for metrics
        metrics_port = config.get('metrics_port', 9090)
        self.http_server = MetricsHttpServer(
            self.metrics_collector, 
            self.health_checker, 
            metrics_port
        )
        
        # Background tasks
        self._monitoring_tasks: List[asyncio.Task] = []
        self._stats_collection_interval = config.get('stats_interval', 30)
        
        # Enable packet capture if configured
        if config.get('packet_capture', {}).get('enabled', False):
            pcap_file = config.get('packet_capture', {}).get('pcap_file')
            self.packet_capture.enable(pcap_file)
    
    async def start(self):
        """Start monitoring system"""
        logger.info("Starting monitoring system")
        
        # Start HTTP server
        await self.http_server.start_server()
        
        # Start background monitoring tasks
        self._monitoring_tasks.append(
            asyncio.create_task(self._stats_collection_loop())
        )
        
        logger.info("Monitoring system started")
    
    async def stop(self):
        """Stop monitoring system"""
        logger.info("Stopping monitoring system")
        
        # Cancel background tasks
        for task in self._monitoring_tasks:
            task.cancel()
        
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
        
        # Stop HTTP server
        await self.http_server.stop_server()
        
        logger.info("Monitoring system stopped")
    
    async def _stats_collection_loop(self):
        """Background task for collecting system statistics"""
        while True:
            try:
                await asyncio.sleep(self._stats_collection_interval)
                
                # Collect system stats (memory, CPU, etc.)
                # This would integrate with system monitoring libraries
                
                # Run health checks
                await self.health_checker.run_health_checks()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stats collection error: {e}")
    
    def record_connection(self, source_ip: str, dest_port: int, success: bool):
        """Record connection attempt"""
        if success:
            self.metrics_collector.counter('connections_total').inc()
            self.metrics_collector.gauge('connections_active').inc()
        else:
            self.metrics_collector.counter('connections_failed').inc()
    
    def record_connection_close(self):
        """Record connection close"""
        self.metrics_collector.gauge('connections_active').dec()
    
    def record_data_transfer(self, bytes_sent: int, bytes_received: int):
        """Record data transfer"""
        if bytes_sent > 0:
            self.metrics_collector.counter('bytes_sent_total').inc(bytes_sent)
        if bytes_received > 0:
            self.metrics_collector.counter('bytes_received_total').inc(bytes_received)
    
    def record_packet_processing(self, processing_time_ms: float):
        """Record packet processing time"""
        self.metrics_collector.histogram('packet_processing_duration').observe(processing_time_ms)
        self.metrics_collector.counter('packets_processed_total').inc()
    
    def record_ppp_frame(self, direction: str):
        """Record PPP frame"""
        if direction == 'sent':
            self.metrics_collector.counter('ppp_frames_sent').inc()
        elif direction == 'received':
            self.metrics_collector.counter('ppp_frames_received').inc()
    
    def record_tcp_segment(self, direction: str):
        """Record TCP segment"""
        if direction == 'sent':
            self.metrics_collector.counter('tcp_segments_sent').inc()
        elif direction == 'received':
            self.metrics_collector.counter('tcp_segments_received').inc()
    
    def record_security_event(self):
        """Record security event"""
        self.metrics_collector.counter('security_events_total').inc()
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get monitoring system status"""
        return {
            'metrics_collector': {
                'total_metrics': len(self.metrics_collector.get_all_metrics())
            },
            'health_checker': {
                'overall_health': self.health_checker.get_overall_health().value,
                'checks_registered': len(self.health_checker._health_checks)
            },
            'packet_capture': {
                'enabled': self.packet_capture._enabled,
                'packets_captured': len(self.packet_capture._packets)
            },
            'http_server': {
                'running': self.http_server._server is not None,
                'port': self.http_server.port
            }
        }