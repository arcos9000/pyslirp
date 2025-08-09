#!/usr/bin/env python3
"""
Simple TCP Data Test for PyLiRP

This creates a basic TCP echo server and sends simple data through
the PPP connection to verify fundamental packet flow is working.
"""

import asyncio
import socket
import struct
import logging

logger = logging.getLogger(__name__)

class SimpleEchoServer:
    """Simple TCP echo server for testing"""
    
    def __init__(self, port=8888):
        self.port = port
        self.server = None
        self.client_count = 0
        
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle client connection"""
        self.client_count += 1
        client_addr = writer.get_extra_info('peername')
        logger.info(f"Echo server: Client #{self.client_count} connected from {client_addr}")
        
        try:
            while True:
                # Read data from client
                data = await reader.read(1024)
                if not data:
                    logger.info(f"Echo server: Client #{self.client_count} disconnected")
                    break
                
                logger.info(f"Echo server: Received {len(data)} bytes: {data[:50]}")
                
                # Echo data back to client
                response = b"ECHO: " + data
                writer.write(response)
                await writer.drain()
                
                logger.info(f"Echo server: Sent {len(response)} bytes back to client")
                
        except Exception as e:
            logger.error(f"Echo server error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            logger.info(f"Echo server: Client #{self.client_count} connection closed")
    
    async def start(self):
        """Start the echo server"""
        self.server = await asyncio.start_server(
            self.handle_client, 
            '127.0.0.1', 
            self.port
        )
        
        logger.info(f"Echo server listening on 127.0.0.1:{self.port}")
        return self.server
    
    async def stop(self):
        """Stop the echo server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Echo server stopped")

class SimpleTCPTester:
    """Simple TCP connection tester"""
    
    def __init__(self):
        self.test_messages = [
            b"Hello World!",
            b"Testing TCP connection",
            b"12345", 
            b"This is a longer test message to verify larger data transfer works correctly",
            b"Final test message"
        ]
    
    async def test_direct_connection(self, host='127.0.0.1', port=8888):
        """Test direct connection to echo server (bypassing PPP)"""
        logger.info(f"Testing direct connection to {host}:{port}")
        
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=5.0
            )
            
            logger.info("Direct connection established")
            
            for i, message in enumerate(self.test_messages):
                logger.info(f"Sending message {i+1}: {message}")
                
                # Send message
                writer.write(message)
                await writer.drain()
                
                # Read response
                response = await asyncio.wait_for(reader.read(1024), timeout=2.0)
                logger.info(f"Received response {i+1}: {response}")
                
                if not response.startswith(b"ECHO: "):
                    logger.error(f"Unexpected response: {response}")
                    return False
                
                await asyncio.sleep(0.1)  # Small delay between messages
            
            writer.close()
            await writer.wait_closed()
            logger.info("Direct connection test completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Direct connection test failed: {e}")
            return False
    
    def create_raw_tcp_packet(self, src_ip="10.0.0.2", dst_ip="10.0.0.1", 
                             src_port=12345, dst_port=8888, 
                             seq=1000, ack=0, flags=0x02, data=b""):
        """Create raw TCP packet for testing PPP flow"""
        
        # TCP header
        tcp_header = struct.pack('!HHIIBBHHH',
            src_port,     # Source port
            dst_port,     # Destination port  
            seq,          # Sequence number
            ack,          # Acknowledgment number
            5 << 4,       # Header length (5 * 4 = 20 bytes)
            flags,        # Flags
            8192,         # Window size
            0,            # Checksum (will calculate)
            0             # Urgent pointer
        )
        
        tcp_segment = tcp_header + data
        
        # Calculate TCP checksum
        src_ip_bytes = socket.inet_aton(src_ip)
        dst_ip_bytes = socket.inet_aton(dst_ip)
        
        # Pseudo-header for checksum
        pseudo_header = struct.pack('!4s4sBBH',
            src_ip_bytes, dst_ip_bytes,
            0, 6,  # Reserved, Protocol (TCP)
            len(tcp_segment)
        )
        
        checksum_data = pseudo_header + tcp_segment
        if len(checksum_data) % 2:
            checksum_data += b'\x00'
        
        checksum = 0
        for i in range(0, len(checksum_data), 2):
            checksum += struct.unpack('!H', checksum_data[i:i+2])[0]
        
        while checksum >> 16:
            checksum = (checksum & 0xFFFF) + (checksum >> 16)
        
        checksum = ~checksum & 0xFFFF
        
        # Update checksum in TCP header
        tcp_segment = tcp_segment[:16] + struct.pack('!H', checksum) + tcp_segment[18:]
        
        # Create IP packet
        ip_header = struct.pack('!BBHHHBBH4s4s',
            (4 << 4) | 5,  # Version and IHL
            0,             # TOS
            20 + len(tcp_segment),  # Total length
            random.randint(0, 65535),  # ID
            0x4000,        # Flags and fragment offset (Don't fragment)
            64,            # TTL
            6,             # Protocol (TCP)
            0,             # Header checksum (will calculate)
            src_ip_bytes,
            dst_ip_bytes
        )
        
        # Calculate IP checksum
        ip_checksum = 0
        for i in range(0, len(ip_header), 2):
            ip_checksum += struct.unpack('!H', ip_header[i:i+2])[0]
        
        while ip_checksum >> 16:
            ip_checksum = (ip_checksum & 0xFFFF) + (ip_checksum >> 16)
        
        ip_checksum = ~ip_checksum & 0xFFFF
        
        # Update IP checksum
        ip_packet = ip_header[:10] + struct.pack('!H', ip_checksum) + ip_header[12:] + tcp_segment
        
        return ip_packet

async def run_simple_test():
    """Run simple TCP test"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Start echo server
    echo_server = SimpleEchoServer(8888)
    server = await echo_server.start()
    
    try:
        # Test direct connection first
        tester = SimpleTCPTester()
        logger.info("=== Testing Direct Connection ===")
        success = await tester.test_direct_connection()
        
        if success:
            logger.info("✅ Direct connection test passed")
        else:
            logger.error("❌ Direct connection test failed")
            return
        
        logger.info("=== Echo Server Ready for PPP Testing ===")
        logger.info("You can now test PPP connection to 127.0.0.1:8888")
        logger.info("Expected behavior:")
        logger.info("1. PPP client connects to 10.0.0.1:8888")
        logger.info("2. Server forwards to 127.0.0.1:8888 (echo server)")
        logger.info("3. Echo server responds with 'ECHO: <your_message>'")
        logger.info("4. Response should flow back to PPP client")
        
        # Keep server running
        async with server:
            await server.serve_forever()
            
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    finally:
        await echo_server.stop()

if __name__ == "__main__":
    asyncio.run(run_simple_test())