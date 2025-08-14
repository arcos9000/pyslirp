#!/usr/bin/env python3
"""
TCP Port Forwarder for PyLiRP Client
Creates local TCP listeners that forward connections through the PPP link
"""

import asyncio
import struct
import socket
import random
import time
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from safe_logger import get_safe_logger

logger = get_safe_logger(__name__)

@dataclass
class ForwardedConnection:
    """Represents a forwarded TCP connection"""
    local_reader: asyncio.StreamReader
    local_writer: asyncio.StreamWriter
    local_port: int
    remote_ip: str
    remote_port: int
    synthetic_port: int  # Port we use on PPP side
    seq_num: int = field(default_factory=lambda: random.randint(1000000, 4000000000))
    ack_num: int = 0
    state: str = "INIT"
    buffer: bytes = b""
    created_at: float = field(default_factory=time.time)

class TCPPortForwarder:
    """Creates local TCP listeners that tunnel through PPP"""
    
    def __init__(self, ppp_bridge):
        self.ppp_bridge = ppp_bridge
        self.listeners = {}
        self.connections = {}  # synthetic_port -> ForwardedConnection
        self.next_synthetic_port = 30000
        self.running = False
        
    def _get_next_synthetic_port(self) -> int:
        """Get next available synthetic port for PPP side"""
        port = self.next_synthetic_port
        self.next_synthetic_port += 1
        if self.next_synthetic_port > 60000:
            self.next_synthetic_port = 30000
        return port
    
    async def create_listener(self, local_port: int, remote_port: int, 
                            local_bind: str = '127.0.0.1'):
        """Create a local TCP listener that forwards to remote service"""
        
        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            """Handle new client connection"""
            client_addr = writer.get_extra_info('peername')
            logger.info(f"New connection on {local_bind}:{local_port} from {client_addr}")
            
            # Create forwarded connection
            synthetic_port = self._get_next_synthetic_port()
            conn = ForwardedConnection(
                local_reader=reader,
                local_writer=writer,
                local_port=local_port,
                remote_ip=self.ppp_bridge.remote_ip,  # Server IP (10.0.0.1)
                remote_port=remote_port,
                synthetic_port=synthetic_port
            )
            
            self.connections[synthetic_port] = conn
            
            try:
                # Initiate TCP connection through PPP
                await self._send_syn(conn)
                
                # Handle bidirectional data forwarding
                await self._handle_connection(conn)
                
            except Exception as e:
                logger.error(f"Error handling connection: {e}")
            finally:
                # Cleanup
                writer.close()
                await writer.wait_closed()
                if synthetic_port in self.connections:
                    del self.connections[synthetic_port]
        
        # Create and start the server
        server = await asyncio.start_server(
            handle_client, local_bind, local_port
        )
        
        self.listeners[local_port] = server
        
        addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
        logger.info(f"TCP forwarder listening on {addrs} -> {self.ppp_bridge.remote_ip}:{remote_port}")
        
        return server
    
    async def _send_syn(self, conn: ForwardedConnection):
        """Send TCP SYN packet through PPP"""
        logger.info(f"Sending SYN: {conn.synthetic_port} -> {conn.remote_ip}:{conn.remote_port} (seq={conn.seq_num})")
        
        # Create TCP SYN packet
        tcp_segment = self._create_tcp_segment(
            conn.synthetic_port,
            conn.remote_port,
            conn.seq_num,
            0,
            flags=0x02,  # SYN
            window=8192
        )
        
        # Send through PPP
        await self._send_tcp_packet(
            self.ppp_bridge.local_ip,
            conn.remote_ip,
            tcp_segment
        )
        
        conn.state = "SYN_SENT"
        logger.info(f"SYN sent, connection {conn.synthetic_port} now in SYN_SENT state")
    
    async def _handle_connection(self, conn: ForwardedConnection):
        """Handle the forwarded connection"""
        try:
            # Create task to read from local client
            read_task = asyncio.create_task(self._read_from_client(conn))
            
            # Wait for connection to complete or fail
            timeout = 10  # 10 second timeout for connection
            start_time = time.time()
            
            while conn.state != "ESTABLISHED":
                if time.time() - start_time > timeout:
                    logger.error(f"Connection timeout for port {conn.synthetic_port}")
                    break
                await asyncio.sleep(0.1)
            
            if conn.state == "ESTABLISHED":
                logger.info(f"Connection established for port {conn.synthetic_port}")
                # Keep connection alive
                await read_task
            
        except Exception as e:
            logger.error(f"Error in connection handler: {e}")
        finally:
            # Send FIN if connection was established
            if conn.state == "ESTABLISHED":
                await self._send_fin(conn)
    
    async def _read_from_client(self, conn: ForwardedConnection):
        """Read data from local client and forward through PPP"""
        try:
            while conn.state in ["SYN_SENT", "ESTABLISHED"]:
                # Read from client with timeout
                try:
                    data = await asyncio.wait_for(
                        conn.local_reader.read(4096),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                if not data:
                    # Client closed connection
                    logger.debug(f"Client closed connection on port {conn.synthetic_port}")
                    break
                
                # Buffer data if not yet established
                if conn.state != "ESTABLISHED":
                    conn.buffer += data
                else:
                    # Send data through PPP
                    await self._send_data(conn, data)
                    
        except Exception as e:
            logger.error(f"Error reading from client: {e}")
    
    async def _send_data(self, conn: ForwardedConnection, data: bytes):
        """Send data through PPP connection"""
        logger.debug(f"Sending {len(data)} bytes from local client through PPP for port {conn.synthetic_port}")
        logger.debug(f"Data packet: seq={conn.seq_num}, ack={conn.ack_num}, data='{data[:20]}'")
        
        # Create TCP data packet
        tcp_segment = self._create_tcp_segment(
            conn.synthetic_port,
            conn.remote_port,
            conn.seq_num,
            conn.ack_num,
            flags=0x18,  # PSH|ACK
            window=8192,
            data=data
        )
        
        # Send through PPP
        await self._send_tcp_packet(
            self.ppp_bridge.local_ip,
            conn.remote_ip,
            tcp_segment
        )
        
        # Update sequence number
        conn.seq_num += len(data)
        logger.debug(f"Sent {len(data)} bytes, updated seq to {conn.seq_num}")
    
    async def _send_fin(self, conn: ForwardedConnection):
        """Send TCP FIN packet"""
        logger.debug(f"Sending FIN for port {conn.synthetic_port}")
        
        tcp_segment = self._create_tcp_segment(
            conn.synthetic_port,
            conn.remote_port,
            conn.seq_num,
            conn.ack_num,
            flags=0x11,  # FIN|ACK
            window=8192
        )
        
        await self._send_tcp_packet(
            self.ppp_bridge.local_ip,
            conn.remote_ip,
            tcp_segment
        )
        
        conn.state = "FIN_SENT"
    
    def _create_tcp_segment(self, src_port: int, dst_port: int, seq: int, ack: int,
                           flags: int, window: int, data: bytes = b"") -> bytes:
        """Create a TCP segment"""
        # TCP header
        tcp_header = struct.pack('!HHIIBBHHH',
            src_port,     # Source port
            dst_port,     # Destination port
            seq,          # Sequence number
            ack,          # Acknowledgment number
            5 << 4,       # Header length (5 * 4 = 20 bytes)
            flags,        # Flags
            window,       # Window size
            0,            # Checksum (placeholder)
            0             # Urgent pointer
        )
        
        tcp_segment = tcp_header + data
        
        # Calculate checksum
        src_ip = socket.inet_aton(self.ppp_bridge.local_ip)
        dst_ip = socket.inet_aton(self.ppp_bridge.remote_ip)
        checksum = self._calculate_tcp_checksum(src_ip, dst_ip, tcp_segment)
        
        # Update checksum in header
        tcp_segment = tcp_segment[:16] + struct.pack('!H', checksum) + tcp_segment[18:]
        
        return tcp_segment
    
    def _calculate_tcp_checksum(self, src_ip: bytes, dst_ip: bytes, tcp_segment: bytes) -> int:
        """Calculate TCP checksum including pseudo-header"""
        # Pseudo-header
        pseudo = struct.pack('!4s4sBBH',
            src_ip, dst_ip,
            0, 6,  # Reserved, Protocol (TCP)
            len(tcp_segment)
        )
        
        data = pseudo + tcp_segment
        if len(data) % 2:
            data += b'\x00'
        
        checksum = 0
        for i in range(0, len(data), 2):
            checksum += struct.unpack('!H', data[i:i+2])[0]
        
        while checksum >> 16:
            checksum = (checksum & 0xFFFF) + (checksum >> 16)
        
        return ~checksum & 0xFFFF
    
    async def _send_tcp_packet(self, src_ip: str, dst_ip: str, tcp_segment: bytes):
        """Send TCP packet through PPP"""
        # Create IP packet
        ip_packet = self._create_ip_packet(
            socket.inet_aton(src_ip),
            socket.inet_aton(dst_ip),
            tcp_segment
        )
        
        # Create PPP frame
        ppp_frame = struct.pack('!BBH', 0xFF, 0x03, 0x0021) + ip_packet
        
        # Frame and send
        from pySLiRP import AsyncPPPHandler
        framed = AsyncPPPHandler.frame_data(ppp_frame)
        
        if hasattr(self.ppp_bridge, 'serial_writer'):
            logger.debug(f"Sending {len(framed)} bytes through serial: {src_ip}->{dst_ip}")
            self.ppp_bridge.serial_writer.write(framed)
            await self.ppp_bridge.serial_writer.drain()
        else:
            logger.error("No serial writer available - packet not sent!")
    
    def _create_ip_packet(self, src_ip: bytes, dst_ip: bytes, payload: bytes) -> bytes:
        """Create an IP packet"""
        # IP header
        version_ihl = (4 << 4) | 5
        tos = 0
        total_length = 20 + len(payload)
        identification = random.randint(0, 65535)
        flags_fragment = 0x4000  # Don't fragment
        ttl = 64
        protocol = 6  # TCP
        checksum = 0
        
        ip_header = struct.pack('!BBHHHBBH4s4s',
            version_ihl, tos, total_length,
            identification, flags_fragment,
            ttl, protocol, checksum,
            src_ip, dst_ip
        )
        
        # Calculate checksum
        checksum = self._calculate_ip_checksum(ip_header)
        
        # Update checksum in header
        ip_header = ip_header[:10] + struct.pack('!H', checksum) + ip_header[12:]
        
        return ip_header + payload
    
    def _calculate_ip_checksum(self, header: bytes) -> int:
        """Calculate IP header checksum"""
        if len(header) % 2:
            header += b'\x00'
        
        checksum = 0
        for i in range(0, len(header), 2):
            checksum += struct.unpack('!H', header[i:i+2])[0]
        
        while checksum >> 16:
            checksum = (checksum & 0xFFFF) + (checksum >> 16)
        
        return ~checksum & 0xFFFF
    
    async def handle_incoming_packet(self, packet_info: Dict):
        """Handle incoming TCP packet from PPP for our forwarded connections"""
        dst_port = packet_info.get('dst_port')
        src_port = packet_info.get('src_port')
        flags = packet_info.get('flags', 0)
        seq_num = packet_info.get('seq', 0)
        ack_num = packet_info.get('ack', 0)
        data = packet_info.get('data', b'')
        
        # Decode flags for debugging
        flag_names = []
        if flags & 0x01: flag_names.append("FIN")
        if flags & 0x02: flag_names.append("SYN")
        if flags & 0x04: flag_names.append("RST")
        if flags & 0x08: flag_names.append("PSH")
        if flags & 0x10: flag_names.append("ACK")
        
        logger.debug(f"Forwarder received: {src_port}->{dst_port}, flags={'/'.join(flag_names) if flag_names else 'NONE'} (0x{flags:02x}), seq={seq_num}, ack={ack_num}, data_len={len(data)}")
        
        if dst_port not in self.connections:
            logger.debug(f"No connection found for port {dst_port}")
            return None
        
        conn = self.connections[dst_port]
        
        # Handle based on current state
        if conn.state == "SYN_SENT" and (flags & 0x12) == 0x12:  # SYN|ACK
            # Connection accepted
            logger.info(f"Received SYN|ACK for port {dst_port} - connection established!")
            conn.ack_num = packet_info.get('seq', 0) + 1
            conn.state = "ESTABLISHED"
            
            # Send ACK
            await self._send_ack(conn)
            
            # Send any buffered data
            if conn.buffer:
                await self._send_data(conn, conn.buffer)
                conn.buffer = b""
                
        elif conn.state == "ESTABLISHED":
            # Handle ACK packets (important for tracking what server has received)
            if flags & 0x10:  # ACK flag
                # Server is acknowledging our sent data
                server_ack = packet_info.get('ack', 0)
                logger.debug(f"Server ACKed up to seq {server_ack}, our current seq is {conn.seq_num}")
                
                # CRITICAL: Update our sequence number to match what server ACKed
                # This ensures we stay in sync with the server's expectations
                if server_ack > conn.seq_num:
                    logger.debug(f"Updating seq from {conn.seq_num} to {server_ack} based on server ACK")
                    conn.seq_num = server_ack
            
            # Handle data packets
            data = packet_info.get('data', b'')
            if data:
                logger.debug(f"Forwarding {len(data)} bytes from server to local client on port {dst_port}")
                # Forward data to local client
                try:
                    conn.local_writer.write(data)
                    await conn.local_writer.drain()
                    logger.debug(f"Successfully forwarded {len(data)} bytes to local client")
                except Exception as e:
                    logger.error(f"Failed to forward data to local client: {e}")
                
                # Update ack number to acknowledge received data
                conn.ack_num = packet_info.get('seq', 0) + len(data)
                
                # Send ACK
                await self._send_ack(conn)
            
            # Handle FIN packets
            if flags & 0x01:  # FIN
                logger.debug(f"Received FIN for port {dst_port}")
                conn.state = "CLOSE_WAIT"
                # Send ACK for FIN
                conn.ack_num = packet_info.get('seq', 0) + 1
                await self._send_ack(conn)
                # Close local connection
                conn.local_writer.close()
    
    async def _send_ack(self, conn: ForwardedConnection):
        """Send TCP ACK packet"""
        tcp_segment = self._create_tcp_segment(
            conn.synthetic_port,
            conn.remote_port,
            conn.seq_num,
            conn.ack_num,
            flags=0x10,  # ACK
            window=8192
        )
        
        await self._send_tcp_packet(
            self.ppp_bridge.local_ip,
            conn.remote_ip,
            tcp_segment
        )
    
    async def start_forwarders(self, config: Any):
        """Start port forwarders based on configuration"""
        logger.info("[FORWARDER] Starting port forwarders...")
        self.running = True
        
        # Default port mappings for client
        default_mappings = {
            2222: 22,   # SSH
            8080: 80,   # HTTP
            8443: 443,  # HTTPS
            8888: 8888, # Echo server for testing
        }
        
        # Use config mappings if available
        if config and hasattr(config, 'port_forwards'):
            logger.info(f"[FORWARDER] Using config port_forwards: {config.port_forwards}")
            mappings = config.port_forwards
        elif config and hasattr(config, 'client_forwards'):
            logger.info(f"[FORWARDER] Using legacy client_forwards: {config.client_forwards}")
            mappings = config.client_forwards  # Legacy support
        else:
            logger.info(f"[FORWARDER] Using default mappings: {default_mappings}")
            mappings = default_mappings
        
        logger.info(f"[FORWARDER] Creating {len(mappings)} port forward listeners...")
        
        for local_port, remote_port in mappings.items():
            try:
                logger.info(f"[FORWARDER] Creating listener on localhost:{local_port} -> {self.ppp_bridge.remote_ip}:{remote_port}")
                await self.create_listener(local_port, remote_port)
                logger.info(f"[SUCCESS] Port forward active: localhost:{local_port} -> {self.ppp_bridge.remote_ip}:{remote_port}")
            except Exception as e:
                logger.error(f"[ERROR] Failed to create listener on port {local_port}: {e}")
        
        logger.info(f"[FORWARDER] Port forwarder setup complete!")
    
    async def stop(self):
        """Stop all port forwarders"""
        self.running = False
        
        # Close all listeners
        for server in self.listeners.values():
            server.close()
            await server.wait_closed()
        
        # Close all connections
        for conn in self.connections.values():
            conn.local_writer.close()
            await conn.local_writer.wait_closed()