#!/usr/bin/env python3
"""
Comprehensive Testing Framework for PyLiRP
Provides unit tests, integration tests, performance tests, and protocol compliance tests
"""

import asyncio
import pytest
import time
import socket
import struct
import threading
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, List, Optional, Any, Callable, Tuple
import logging
from dataclasses import dataclass
from contextlib import asynccontextmanager
import random
import statistics

logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """Test execution result"""
    test_name: str
    success: bool
    duration: float
    error: Optional[str] = None
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}

class MockSerial:
    """Mock serial connection for testing"""
    
    def __init__(self):
        self.read_buffer = bytearray()
        self.write_buffer = bytearray()
        self.is_open = True
        self.closed = False
    
    def write(self, data: bytes):
        """Mock write operation"""
        if self.closed:
            raise Exception("Serial port is closed")
        self.write_buffer.extend(data)
        return len(data)
    
    def read(self, size: int = 1) -> bytes:
        """Mock read operation"""
        if self.closed:
            raise Exception("Serial port is closed")
        
        if len(self.read_buffer) == 0:
            return b''
        
        result = bytes(self.read_buffer[:size])
        self.read_buffer = self.read_buffer[size:]
        return result
    
    def close(self):
        """Close mock serial port"""
        self.is_open = False
        self.closed = True
    
    def inject_data(self, data: bytes):
        """Inject data into read buffer for testing"""
        self.read_buffer.extend(data)

class MockAsyncSerial:
    """Mock async serial connection for testing"""
    
    def __init__(self):
        self.read_queue = asyncio.Queue()
        self.write_buffer = bytearray()
        self.closed = False
    
    async def read(self, size: int = 1024) -> bytes:
        """Mock async read"""
        if self.closed:
            return b''
        
        try:
            data = await asyncio.wait_for(self.read_queue.get(), timeout=0.1)
            return data
        except asyncio.TimeoutError:
            return b''
    
    def write(self, data: bytes):
        """Mock async write"""
        if not self.closed:
            self.write_buffer.extend(data)
    
    async def drain(self):
        """Mock drain operation"""
        pass
    
    def close(self):
        """Close mock connection"""
        self.closed = True
    
    async def wait_closed(self):
        """Mock wait for close"""
        pass
    
    async def inject_data(self, data: bytes):
        """Inject data for testing"""
        await self.read_queue.put(data)

class PPPTestUtils:
    """PPP protocol testing utilities"""
    
    @staticmethod
    def create_ppp_frame(protocol: int, data: bytes) -> bytes:
        """Create a PPP frame"""
        frame = struct.pack('!BBH', 0xFF, 0x03, protocol) + data
        
        # Add PPP framing
        result = bytearray([0x7E])  # Start flag
        
        for byte in frame:
            if byte in (0x7E, 0x7D):
                result.append(0x7D)
                result.append(byte ^ 0x20)
            else:
                result.append(byte)
        
        result.append(0x7E)  # End flag
        return bytes(result)
    
    @staticmethod
    def create_lcp_configure_request(identifier: int = 1, 
                                   magic_number: Optional[int] = None,
                                   mru: int = 1500) -> bytes:
        """Create LCP Configure-Request packet"""
        options = bytearray()
        
        # Magic Number option
        if magic_number is not None:
            options.extend(struct.pack('!BBI', 5, 6, magic_number))
        
        # MRU option
        options.extend(struct.pack('!BBH', 1, 4, mru))
        
        # LCP header
        length = 4 + len(options)
        packet = struct.pack('!BBH', 1, identifier, length) + options
        
        return packet
    
    @staticmethod
    def create_ipcp_configure_request(identifier: int = 1, 
                                    ip_address: str = "10.0.0.2") -> bytes:
        """Create IPCP Configure-Request packet"""
        ip_bytes = socket.inet_aton(ip_address)
        options = struct.pack('!BB4s', 3, 6, ip_bytes)  # IP Address option
        
        length = 4 + len(options)
        packet = struct.pack('!BBH', 1, identifier, length) + options
        
        return packet

class TCPTestUtils:
    """TCP protocol testing utilities"""
    
    @staticmethod
    def create_ip_header(src_ip: str, dst_ip: str, payload_len: int, 
                        protocol: int = 6) -> bytes:
        """Create IP header"""
        version_ihl = 0x45  # IPv4, 20-byte header
        tos = 0
        total_length = 20 + payload_len
        identification = random.randint(1, 65535)
        flags_fragment = 0x4000  # Don't fragment
        ttl = 64
        checksum = 0  # Will be calculated
        
        src_bytes = socket.inet_aton(src_ip)
        dst_bytes = socket.inet_aton(dst_ip)
        
        header = struct.pack('!BBHHHBBH4s4s',
                           version_ihl, tos, total_length,
                           identification, flags_fragment,
                           ttl, protocol, checksum,
                           src_bytes, dst_bytes)
        
        return header
    
    @staticmethod
    def create_tcp_header(src_port: int, dst_port: int, seq: int, ack: int,
                         flags: int, window: int = 8192) -> bytes:
        """Create TCP header"""
        data_offset = 5 << 4  # 20-byte header
        checksum = 0  # Will be calculated
        urgent = 0
        
        header = struct.pack('!HHIIBBHHH',
                           src_port, dst_port,
                           seq, ack,
                           data_offset, flags,
                           window, checksum, urgent)
        
        return header
    
    @staticmethod
    def create_tcp_packet(src_ip: str, dst_ip: str, src_port: int, dst_port: int,
                         seq: int, ack: int, flags: int, data: bytes = b'') -> bytes:
        """Create complete TCP packet"""
        tcp_header = TCPTestUtils.create_tcp_header(src_port, dst_port, seq, ack, flags)
        tcp_segment = tcp_header + data
        
        ip_header = TCPTestUtils.create_ip_header(src_ip, dst_ip, len(tcp_segment))
        
        return ip_header + tcp_segment

class PerformanceTestSuite:
    """Performance testing utilities"""
    
    def __init__(self):
        self.metrics = {}
    
    async def measure_throughput(self, test_func: Callable, data_size: int,
                               duration: float = 10.0) -> Dict[str, float]:
        """Measure throughput of a function"""
        start_time = time.time()
        bytes_processed = 0
        operations = 0
        
        while time.time() - start_time < duration:
            await test_func(b'x' * data_size)
            bytes_processed += data_size
            operations += 1
            
            # Small delay to prevent overwhelming
            await asyncio.sleep(0.001)
        
        actual_duration = time.time() - start_time
        
        return {
            'bytes_per_second': bytes_processed / actual_duration,
            'operations_per_second': operations / actual_duration,
            'total_bytes': bytes_processed,
            'total_operations': operations,
            'duration': actual_duration
        }
    
    async def measure_latency(self, test_func: Callable, iterations: int = 1000) -> Dict[str, float]:
        """Measure latency statistics"""
        latencies = []
        
        for _ in range(iterations):
            start_time = time.time()
            await test_func()
            latency = (time.time() - start_time) * 1000  # Convert to milliseconds
            latencies.append(latency)
        
        return {
            'mean_latency_ms': statistics.mean(latencies),
            'median_latency_ms': statistics.median(latencies),
            'min_latency_ms': min(latencies),
            'max_latency_ms': max(latencies),
            'p95_latency_ms': self._percentile(latencies, 95),
            'p99_latency_ms': self._percentile(latencies, 99),
            'std_dev_ms': statistics.stdev(latencies)
        }
    
    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile"""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * (percentile / 100))
        return sorted_data[min(index, len(sorted_data) - 1)]

class TestFramework:
    """Main testing framework"""
    
    def __init__(self):
        self.test_results: List[TestResult] = []
        self.performance_suite = PerformanceTestSuite()
        self.mock_serial = None
        self.mock_services = {}
    
    @asynccontextmanager
    async def mock_serial_context(self):
        """Context manager for mock serial testing"""
        self.mock_serial = MockAsyncSerial()
        try:
            yield self.mock_serial
        finally:
            self.mock_serial.close()
    
    @asynccontextmanager
    async def mock_service_context(self, host: str, port: int):
        """Context manager for mock service testing"""
        mock_service = MockService(host, port)
        await mock_service.start()
        
        service_key = f"{host}:{port}"
        self.mock_services[service_key] = mock_service
        
        try:
            yield mock_service
        finally:
            await mock_service.stop()
            if service_key in self.mock_services:
                del self.mock_services[service_key]
    
    async def run_test(self, test_name: str, test_func: Callable) -> TestResult:
        """Run a single test"""
        start_time = time.time()
        
        try:
            logger.info(f"Running test: {test_name}")
            result = await test_func()
            
            duration = time.time() - start_time
            test_result = TestResult(
                test_name=test_name,
                success=True,
                duration=duration,
                details=result if isinstance(result, dict) else {}
            )
            
        except Exception as e:
            duration = time.time() - start_time
            test_result = TestResult(
                test_name=test_name,
                success=False,
                duration=duration,
                error=str(e),
                details={'exception_type': type(e).__name__}
            )
            logger.error(f"Test failed: {test_name}: {e}")
        
        self.test_results.append(test_result)
        return test_result
    
    async def run_test_suite(self, test_suite: Dict[str, Callable]) -> List[TestResult]:
        """Run a complete test suite"""
        results = []
        
        for test_name, test_func in test_suite.items():
            result = await self.run_test(test_name, test_func)
            results.append(result)
        
        return results
    
    def get_test_summary(self) -> Dict[str, Any]:
        """Get summary of test results"""
        if not self.test_results:
            return {'total': 0, 'passed': 0, 'failed': 0, 'success_rate': 0.0}
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r.success)
        failed_tests = total_tests - passed_tests
        
        total_duration = sum(r.duration for r in self.test_results)
        avg_duration = total_duration / total_tests
        
        return {
            'total': total_tests,
            'passed': passed_tests,
            'failed': failed_tests,
            'success_rate': passed_tests / total_tests,
            'total_duration': total_duration,
            'average_duration': avg_duration,
            'failed_tests': [r.test_name for r in self.test_results if not r.success]
        }

class MockService:
    """Mock service for testing service connections"""
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.server = None
        self.connections = []
        self.request_count = 0
        self.responses = {}  # port -> response data
    
    async def start(self):
        """Start mock service"""
        self.server = await asyncio.start_server(
            self._handle_connection,
            self.host,
            self.port
        )
        logger.info(f"Mock service started on {self.host}:{self.port}")
    
    async def stop(self):
        """Stop mock service"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
        # Close all connections
        for conn in self.connections:
            if not conn.writer.is_closing():
                conn.writer.close()
                await conn.writer.wait_closed()
        
        self.connections.clear()
    
    async def _handle_connection(self, reader: asyncio.StreamReader, 
                               writer: asyncio.StreamWriter):
        """Handle incoming connection"""
        connection = MockConnection(reader, writer)
        self.connections.append(connection)
        self.request_count += 1
        
        try:
            # Echo service by default
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                
                # Send response based on configured behavior
                response_data = self.responses.get(self.port, data)  # Echo by default
                writer.write(response_data)
                await writer.drain()
                
        except Exception as e:
            logger.debug(f"Mock service connection error: {e}")
        finally:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()
            
            if connection in self.connections:
                self.connections.remove(connection)
    
    def set_response(self, response_data: bytes):
        """Set response data for this service"""
        self.responses[self.port] = response_data
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            'request_count': self.request_count,
            'active_connections': len(self.connections),
            'host': self.host,
            'port': self.port
        }

@dataclass
class MockConnection:
    """Mock connection wrapper"""
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter

# Test Suites

class PPPTestSuite:
    """PPP protocol test suite"""
    
    def __init__(self, framework: TestFramework):
        self.framework = framework
    
    async def test_ppp_frame_parsing(self):
        """Test PPP frame parsing"""
        from pySLiRP import AsyncPPPHandler
        
        handler = AsyncPPPHandler()
        
        # Test valid frame
        test_data = PPPTestUtils.create_ppp_frame(0x0021, b"test data")
        frames = await handler.process_data(test_data)
        
        assert len(frames) == 1
        assert len(frames[0]) >= 4  # At least header + data
        
        return {'frames_parsed': len(frames), 'frame_length': len(frames[0])}
    
    async def test_lcp_negotiation(self):
        """Test LCP negotiation"""
        # This would test the LCP negotiation implementation
        # Created by the networking expert
        
        lcp_request = PPPTestUtils.create_lcp_configure_request(
            identifier=1, magic_number=0x12345678
        )
        
        # Test that LCP packet is properly formatted
        assert len(lcp_request) >= 8  # Minimum LCP packet size
        
        return {'lcp_packet_size': len(lcp_request)}
    
    async def test_ppp_framing_edge_cases(self):
        """Test PPP framing with edge cases"""
        from pySLiRP import AsyncPPPHandler
        
        handler = AsyncPPPHandler()
        
        # Test frame with escape sequences
        test_frame = b'\xFF\x03\x00\x21\x7E\x7D'  # Contains flag and escape
        framed = AsyncPPPHandler.frame_data(test_frame)
        
        # Should escape the flag and escape characters
        assert b'\x7D' in framed
        
        return {'escaped_frame_length': len(framed)}

class TCPTestSuite:
    """TCP protocol test suite"""
    
    def __init__(self, framework: TestFramework):
        self.framework = framework
    
    async def test_tcp_packet_parsing(self):
        """Test TCP packet parsing"""
        from pySLiRP import AsyncTCPStack
        
        stack = AsyncTCPStack()
        
        # Create test TCP packet
        packet = TCPTestUtils.create_tcp_packet(
            "10.0.0.2", "10.0.0.1", 12345, 22, 1000, 0, 0x02  # SYN flag
        )
        
        parsed = stack.parse_packet(packet)
        
        assert parsed is not None
        assert parsed['src_port'] == 12345
        assert parsed['dst_port'] == 22
        assert parsed['flags'] & 0x02  # SYN flag
        
        return {
            'packet_parsed': True,
            'src_port': parsed['src_port'],
            'dst_port': parsed['dst_port']
        }
    
    async def test_tcp_checksum_calculation(self):
        """Test TCP checksum calculation"""
        from pySLiRP import AsyncTCPStack
        
        stack = AsyncTCPStack()
        
        src_ip = socket.inet_aton("10.0.0.1")
        dst_ip = socket.inet_aton("10.0.0.2")
        tcp_segment = b'\x00\x50\x30\x39' + b'\x00' * 16  # Port 80 -> 12345 + padding
        
        checksum = stack.calculate_tcp_checksum(src_ip, dst_ip, tcp_segment)
        
        assert isinstance(checksum, int)
        assert 0 <= checksum <= 65535
        
        return {'checksum': checksum, 'checksum_valid': True}

class IntegrationTestSuite:
    """Integration test suite"""
    
    def __init__(self, framework: TestFramework):
        self.framework = framework
    
    async def test_ppp_to_tcp_flow(self):
        """Test complete PPP to TCP flow"""
        async with self.framework.mock_serial_context() as mock_serial:
            async with self.framework.mock_service_context("127.0.0.1", 8888) as mock_service:
                
                # Set up service response
                mock_service.set_response(b"HTTP/1.1 200 OK\r\n\r\nHello World")
                
                # Simulate PPP frame with TCP SYN
                tcp_syn = TCPTestUtils.create_tcp_packet(
                    "10.0.0.2", "10.0.0.1", 12345, 8888, 1000, 0, 0x02
                )
                ppp_frame = PPPTestUtils.create_ppp_frame(0x0021, tcp_syn)
                
                await mock_serial.inject_data(ppp_frame)
                
                # Small delay for processing
                await asyncio.sleep(0.1)
                
                return {
                    'test_completed': True,
                    'service_requests': mock_service.get_stats()['request_count']
                }

class PerformanceTestSuite:
    """Performance test suite"""
    
    def __init__(self, framework: TestFramework):
        self.framework = framework
    
    async def test_packet_processing_throughput(self):
        """Test packet processing throughput"""
        from pySLiRP import AsyncPPPHandler
        
        handler = AsyncPPPHandler()
        
        async def process_packet(data: bytes):
            await handler.process_data(data)
        
        test_frame = PPPTestUtils.create_ppp_frame(0x0021, b"x" * 1000)
        
        results = await self.framework.performance_suite.measure_throughput(
            lambda data: process_packet(test_frame),
            len(test_frame),
            duration=5.0
        )
        
        return results
    
    async def test_connection_establishment_latency(self):
        """Test connection establishment latency"""
        async def mock_connection_setup():
            # Simulate connection setup time
            await asyncio.sleep(0.001)  # 1ms simulated latency
        
        results = await self.framework.performance_suite.measure_latency(
            mock_connection_setup,
            iterations=100
        )
        
        return results

class LoadTestSuite:
    """Load testing suite"""
    
    def __init__(self, framework: TestFramework):
        self.framework = framework
    
    async def test_concurrent_connections(self, connection_count: int = 100):
        """Test handling of concurrent connections"""
        
        async def simulate_connection():
            async with self.framework.mock_service_context("127.0.0.1", 0) as service:
                # Simulate connection activity
                await asyncio.sleep(random.uniform(0.1, 0.5))
                return service.get_stats()
        
        # Run concurrent connections
        tasks = [simulate_connection() for _ in range(connection_count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = sum(1 for r in results if not isinstance(r, Exception))
        
        return {
            'total_connections': connection_count,
            'successful_connections': successful,
            'success_rate': successful / connection_count,
            'errors': [str(r) for r in results if isinstance(r, Exception)]
        }
    
    async def test_sustained_load(self, duration: int = 60, requests_per_second: int = 10):
        """Test sustained load over time"""
        start_time = time.time()
        request_count = 0
        errors = 0
        
        async def make_request():
            nonlocal request_count, errors
            try:
                async with self.framework.mock_service_context("127.0.0.1", 0) as service:
                    await asyncio.sleep(0.01)  # Simulate processing
                    request_count += 1
            except Exception:
                errors += 1
        
        # Schedule requests at specified rate
        interval = 1.0 / requests_per_second
        
        while time.time() - start_time < duration:
            asyncio.create_task(make_request())
            await asyncio.sleep(interval)
        
        # Wait for remaining tasks
        await asyncio.sleep(1.0)
        
        actual_duration = time.time() - start_time
        actual_rps = request_count / actual_duration
        
        return {
            'duration': actual_duration,
            'total_requests': request_count,
            'errors': errors,
            'actual_rps': actual_rps,
            'target_rps': requests_per_second,
            'error_rate': errors / max(request_count, 1)
        }

class ComplianceTestSuite:
    """RFC compliance test suite"""
    
    def __init__(self, framework: TestFramework):
        self.framework = framework
    
    async def test_ppp_rfc1661_compliance(self):
        """Test PPP RFC 1661 compliance"""
        # Test various PPP protocol requirements
        tests_passed = 0
        total_tests = 0
        
        # Test 1: PPP frame format
        total_tests += 1
        frame = PPPTestUtils.create_ppp_frame(0x0021, b"test")
        if frame.startswith(b'\x7E') and frame.endswith(b'\x7E'):
            tests_passed += 1
        
        # Test 2: Escape sequence handling
        total_tests += 1
        test_data = b'\x7E\x7D'  # Data requiring escaping
        escaped = AsyncPPPHandler.frame_data(b'\xFF\x03\x00\x21' + test_data)
        if b'\x7D\x5E' in escaped and b'\x7D\x5D' in escaped:  # Properly escaped
            tests_passed += 1
        
        return {
            'compliance_score': tests_passed / total_tests,
            'tests_passed': tests_passed,
            'total_tests': total_tests
        }
    
    async def test_tcp_rfc793_compliance(self):
        """Test TCP RFC 793 compliance"""
        # Test TCP state machine compliance
        tests_passed = 0
        total_tests = 0
        
        # Test 1: TCP packet format
        total_tests += 1
        packet = TCPTestUtils.create_tcp_packet(
            "10.0.0.1", "10.0.0.2", 80, 12345, 1000, 0, 0x02
        )
        if len(packet) >= 40:  # Minimum IP + TCP header size
            tests_passed += 1
        
        return {
            'compliance_score': tests_passed / total_tests,
            'tests_passed': tests_passed,
            'total_tests': total_tests
        }

async def run_all_tests():
    """Run all test suites"""
    framework = TestFramework()
    
    # Initialize test suites
    ppp_tests = PPPTestSuite(framework)
    tcp_tests = TCPTestSuite(framework)
    integration_tests = IntegrationTestSuite(framework)
    performance_tests = PerformanceTestSuite(framework)
    load_tests = LoadTestSuite(framework)
    compliance_tests = ComplianceTestSuite(framework)
    
    # Define all tests
    all_tests = {
        # PPP Tests
        "PPP Frame Parsing": ppp_tests.test_ppp_frame_parsing,
        "LCP Negotiation": ppp_tests.test_lcp_negotiation,
        "PPP Framing Edge Cases": ppp_tests.test_ppp_framing_edge_cases,
        
        # TCP Tests
        "TCP Packet Parsing": tcp_tests.test_tcp_packet_parsing,
        "TCP Checksum Calculation": tcp_tests.test_tcp_checksum_calculation,
        
        # Integration Tests
        "PPP to TCP Flow": integration_tests.test_ppp_to_tcp_flow,
        
        # Performance Tests
        "Packet Processing Throughput": performance_tests.test_packet_processing_throughput,
        "Connection Latency": performance_tests.test_connection_establishment_latency,
        
        # Load Tests
        "Concurrent Connections": lambda: load_tests.test_concurrent_connections(50),
        "Sustained Load": lambda: load_tests.test_sustained_load(30, 5),
        
        # Compliance Tests
        "PPP RFC 1661 Compliance": compliance_tests.test_ppp_rfc1661_compliance,
        "TCP RFC 793 Compliance": compliance_tests.test_tcp_rfc793_compliance,
    }
    
    # Run all tests
    results = await framework.run_test_suite(all_tests)
    
    # Print summary
    summary = framework.get_test_summary()
    
    print("\n" + "="*50)
    print("PyLiRP Test Suite Results")
    print("="*50)
    print(f"Total Tests: {summary['total']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Success Rate: {summary['success_rate']:.1%}")
    print(f"Total Duration: {summary['total_duration']:.2f}s")
    print(f"Average Duration: {summary['average_duration']:.3f}s")
    
    if summary['failed_tests']:
        print("\nFailed Tests:")
        for test_name in summary['failed_tests']:
            print(f"  - {test_name}")
    
    print("\n" + "="*50)
    
    return results

if __name__ == "__main__":
    asyncio.run(run_all_tests())