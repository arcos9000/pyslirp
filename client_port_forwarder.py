#!/usr/bin/env python3
"""
Client-side port forwarder for PyLiRP
Creates local TCP listeners that forward connections through PPP to remote services
"""

import asyncio
import struct
import socket
import logging
from typing import Dict, Tuple, Optional
import random

logger = logging.getLogger(__name__)

class ClientPortForwarder:
    """Creates local TCP listeners that forward through PPP"""
    
    def __init__(self, ppp_bridge):
        self.ppp_bridge = ppp_bridge
        self.listeners = {}
        self.forward_mappings = {}
        self.client_connections = {}
        
    async def create_port_forward(self, local_port: int, remote_ip: str, remote_port: int, local_bind: str = '127.0.0.1'):
        """Create a local listener that forwards to remote service through PPP"""
        
        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            """Handle incoming client connection on local port"""
            client_addr = writer.get_extra_info('peername')
            logger.info(f"New connection on {local_bind}:{local_port} from {client_addr}")
            
            # Generate unique local port for this connection
            conn_id = random.randint(30000, 60000)
            
            try:
                # Create synthetic TCP SYN packet to remote service through PPP
                logger.info(f"Forwarding to {remote_ip}:{remote_port} through PPP")
                
                # Store the client connection for later data forwarding
                self.client_connections[conn_id] = {
                    'reader': reader,
                    'writer': writer,
                    'remote_ip': remote_ip,
                    'remote_port': remote_port,
                    'local_port': conn_id
                }
                
                # Initiate TCP connection through PPP
                await self.initiate_ppp_connection(conn_id, remote_ip, remote_port)
                
                # Forward data bidirectionally
                await self.forward_client_data(conn_id, reader, writer)
                
            except Exception as e:
                logger.error(f"Error handling client connection: {e}")
            finally:
                writer.close()
                await writer.wait_closed()
                if conn_id in self.client_connections:
                    del self.client_connections[conn_id]
        
        # Create local TCP listener
        server = await asyncio.start_server(
            handle_client, local_bind, local_port
        )
        
        self.listeners[local_port] = server
        self.forward_mappings[local_port] = (remote_ip, remote_port)
        
        addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
        logger.info(f"Port forward created: {addrs} -> {remote_ip}:{remote_port}")
        
        return server
    
    async def initiate_ppp_connection(self, local_port: int, remote_ip: str, remote_port: int):
        """Send TCP SYN through PPP to initiate connection"""
        # This needs to integrate with the PPP bridge's TCP stack
        # Create a SYN packet and send it through the PPP link
        
        tcp_stack = self.ppp_bridge.tcp_stack
        
        # Convert IP addresses
        src_ip = socket.inet_aton(self.ppp_bridge.local_ip)  # Client IP (10.0.0.2)
        dst_ip = socket.inet_aton(remote_ip)  # Server IP (10.0.0.1)
        
        # Create SYN segment
        seq_num = random.randint(1000000, 4000000000)
        
        # Build TCP header with SYN flag
        tcp_header = struct.pack('!HHIIBBHHH',
            local_port,      # Source port
            remote_port,     # Destination port
            seq_num,         # Sequence number
            0,               # Acknowledgment number
            5 << 4,          # Header length (5 * 4 = 20 bytes)
            0x02,            # Flags (SYN)
            8192,            # Window size
            0,               # Checksum (placeholder)
            0                # Urgent pointer
        )
        
        # Calculate checksum
        pseudo_header = struct.pack('!4s4sBBH',
            src_ip, dst_ip, 0, 6, len(tcp_header)
        )
        checksum = tcp_stack.calculate_tcp_checksum(src_ip, dst_ip, tcp_header)
        
        # Rebuild TCP header with checksum
        tcp_header = tcp_header[:16] + struct.pack('!H', checksum) + tcp_header[18:]
        
        # Create IP packet
        ip_packet = tcp_stack.create_ip_packet(src_ip, dst_ip, tcp_header)
        
        # Send through PPP
        ppp_frame = struct.pack('!BBH', 0xFF, 0x03, 0x0021) + ip_packet
        from pySLiRP import AsyncPPPHandler
        framed = AsyncPPPHandler.frame_data(ppp_frame)
        
        # Get the serial writer from the bridge
        # This assumes we have access to the serial writer
        if hasattr(self.ppp_bridge, 'serial_writer'):
            self.ppp_bridge.serial_writer.write(framed)
            await self.ppp_bridge.serial_writer.drain()
            logger.info(f"Sent SYN for {local_port} -> {remote_ip}:{remote_port}")
    
    async def forward_client_data(self, conn_id: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Forward data from client to PPP and vice versa"""
        try:
            while True:
                # Read from client
                data = await reader.read(4096)
                if not data:
                    break
                
                # Send through PPP (this needs proper integration)
                await self.send_data_through_ppp(conn_id, data)
                
        except Exception as e:
            logger.error(f"Error forwarding data: {e}")
    
    async def send_data_through_ppp(self, conn_id: int, data: bytes):
        """Send data through PPP connection"""
        if conn_id not in self.client_connections:
            return
        
        conn = self.client_connections[conn_id]
        
        # This needs to integrate with the PPP bridge's TCP stack
        # to send data packets through the established connection
        logger.debug(f"Sending {len(data)} bytes through PPP for connection {conn_id}")
    
    async def receive_from_ppp(self, conn_id: int, data: bytes):
        """Receive data from PPP and forward to client"""
        if conn_id not in self.client_connections:
            return
        
        conn = self.client_connections[conn_id]
        conn['writer'].write(data)
        await conn['writer'].drain()
    
    async def start_port_forwards(self, mappings: Dict[int, Tuple[str, int]]):
        """Start multiple port forwards from configuration"""
        for local_port, (remote_ip, remote_port) in mappings.items():
            try:
                await self.create_port_forward(local_port, remote_ip, remote_port)
            except Exception as e:
                logger.error(f"Failed to create port forward {local_port}: {e}")
    
    async def stop(self):
        """Stop all port forwarders"""
        for server in self.listeners.values():
            server.close()
            await server.wait_closed()
        
        for conn in self.client_connections.values():
            conn['writer'].close()
            await conn['writer'].wait_closed()