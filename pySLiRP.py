#!/usr/bin/env python3
"""
Async Python SLiRP implementation with proper TCP state machine
Provides PPP over serial to local services/SOCKS proxy bridge
"""

import asyncio
import struct
import socket
import serial_asyncio
from safe_logger import get_safe_logger
import random
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple, Any, List, NamedTuple
from enum import IntEnum, auto
import time
import heapq
from collections import deque
import math

# Logging is now handled by safe_logger in main.py
logger = get_safe_logger(__name__)

# PPP Protocol Constants
class PPPProtocol:
    """PPP Protocol Numbers (RFC 1661)"""
    IP = 0x0021
    IPCP = 0x8021
    LCP = 0xC021
    PAP = 0xC023
    CHAP = 0xC223

# PPP Control Protocol Codes
class PPPCode:
    """PPP Control Protocol Codes (RFC 1661)"""
    CONFIGURE_REQUEST = 1
    CONFIGURE_ACK = 2
    CONFIGURE_NAK = 3
    CONFIGURE_REJECT = 4
    TERMINATE_REQUEST = 5
    TERMINATE_ACK = 6
    CODE_REJECT = 7
    PROTOCOL_REJECT = 8
    ECHO_REQUEST = 9
    ECHO_REPLY = 10
    DISCARD_REQUEST = 11

# LCP Configuration Options
class LCPOption:
    """LCP Configuration Option Types (RFC 1661)"""
    MRU = 1
    ACCM = 2
    AUTH_PROTOCOL = 3
    QUALITY_PROTOCOL = 4
    MAGIC_NUMBER = 5
    PROTOCOL_COMPRESSION = 7
    ADDR_CONTROL_COMPRESSION = 8

# IPCP Configuration Options
class IPCPOption:
    """IPCP Configuration Option Types (RFC 1332)"""
    IP_ADDRESSES = 1  # Deprecated
    IP_COMPRESSION = 2
    IP_ADDRESS = 3
    MOBILE_IP = 4
    PRIMARY_DNS = 129
    SECONDARY_DNS = 131

# PPP State Machine
class PPPState(IntEnum):
    """PPP State Machine States (RFC 1661)"""
    INITIAL = auto()
    STARTING = auto()
    CLOSED = auto()
    STOPPED = auto()
    CLOSING = auto()
    STOPPING = auto()
    REQUEST_SENT = auto()
    ACK_RECEIVED = auto()
    ACK_SENT = auto()
    OPENED = auto()

@dataclass
class PPPConfigOption:
    """PPP Configuration Option"""
    type: int
    length: int
    data: bytes

@dataclass
class PPPPacket:
    """PPP Control Protocol Packet"""
    code: int
    identifier: int
    length: int
    data: bytes

# TCP States
class TCPState(IntEnum):
    CLOSED = auto()
    LISTEN = auto()
    SYN_SENT = auto()
    SYN_RCVD = auto()
    ESTABLISHED = auto()
    FIN_WAIT_1 = auto()
    FIN_WAIT_2 = auto()
    CLOSE_WAIT = auto()
    CLOSING = auto()
    LAST_ACK = auto()
    TIME_WAIT = auto()

# TCP Flags
class TCPFlags:
    FIN = 0x01
    SYN = 0x02
    RST = 0x04
    PSH = 0x08
    ACK = 0x10
    URG = 0x20

# TCP Timer Types
class TCPTimerType(IntEnum):
    RETRANSMISSION = auto()
    KEEPALIVE = auto()
    TIME_WAIT = auto()
    DELAYED_ACK = auto()
    CONNECT_TIMEOUT = auto()

# TCP Options
class TCPOption:
    END_OF_OPTION_LIST = 0
    NO_OPERATION = 1
    MSS = 2
    WINDOW_SCALE = 3
    SACK_PERMITTED = 4
    SACK = 5
    TIMESTAMP = 8

@dataclass
class TCPTimer:
    """TCP Timer for various timeouts"""
    timer_type: TCPTimerType
    expire_time: float
    callback_data: Any = None
    
    def __lt__(self, other):
        return self.expire_time < other.expire_time

@dataclass
class TCPSegment:
    """Represents a TCP segment for retransmission queue"""
    seq_start: int
    seq_end: int
    data: bytes
    flags: int
    timestamp: float
    retransmit_count: int = 0
    
    def __post_init__(self):
        if self.seq_end == 0:
            self.seq_end = self.seq_start + len(self.data)
            if self.flags & (TCPFlags.SYN | TCPFlags.FIN):
                self.seq_end += 1

class RTTEstimator:
    """RTT estimation for retransmission timeout calculation (RFC 6298)"""
    
    def __init__(self):
        self.srtt = 0.0  # Smoothed RTT
        self.rttvar = 0.0  # RTT variation
        self.rto = 1.0  # Retransmission timeout
        self.first_sample = True
        
    def update_rtt(self, sample_rtt: float):
        """Update RTT estimation with new sample"""
        if self.first_sample:
            self.srtt = sample_rtt
            self.rttvar = sample_rtt / 2.0
            self.first_sample = False
        else:
            # RFC 6298 formulas
            alpha = 0.125
            beta = 0.25
            self.rttvar = (1 - beta) * self.rttvar + beta * abs(self.srtt - sample_rtt)
            self.srtt = (1 - alpha) * self.srtt + alpha * sample_rtt
        
        # Calculate RTO with bounds
        self.rto = max(1.0, min(60.0, self.srtt + max(0.1, 4 * self.rttvar)))
        
    def get_rto(self) -> float:
        """Get current retransmission timeout"""
        return self.rto

class CongestionControl:
    """TCP Congestion Control implementation (Reno with NewReno fast recovery)"""
    
    def __init__(self, mss: int = 1460):
        self.mss = mss
        self.cwnd = float(mss)  # Congestion window
        self.ssthresh = 65535  # Slow start threshold
        self.duplicate_acks = 0
        self.fast_recovery = False
        self.recovery_point = 0
        self.bytes_acked = 0
        
    def on_ack(self, acked_bytes: int, is_duplicate: bool = False):
        """Handle ACK reception"""
        if is_duplicate:
            self.duplicate_acks += 1
            if self.duplicate_acks >= 3 and not self.fast_recovery:
                # Fast retransmit
                self.enter_fast_recovery()
            elif self.fast_recovery:
                # Inflate window during fast recovery
                self.cwnd += self.mss
        else:
            # New data acknowledged
            self.duplicate_acks = 0
            
            if self.fast_recovery:
                if acked_bytes >= (self.recovery_point - self.recovery_point // 2):
                    # Exit fast recovery
                    self.exit_fast_recovery()
                    
            if not self.fast_recovery:
                if self.cwnd < self.ssthresh:
                    # Slow start
                    self.cwnd += min(acked_bytes, self.mss)
                else:
                    # Congestion avoidance
                    self.bytes_acked += acked_bytes
                    if self.bytes_acked >= self.cwnd:
                        self.cwnd += self.mss
                        self.bytes_acked = 0
                        
    def on_timeout(self):
        """Handle retransmission timeout"""
        self.ssthresh = max(self.cwnd // 2, 2 * self.mss)
        self.cwnd = float(self.mss)
        self.duplicate_acks = 0
        self.fast_recovery = False
        
    def enter_fast_recovery(self):
        """Enter fast recovery phase"""
        self.ssthresh = max(self.cwnd // 2, 2 * self.mss)
        self.cwnd = self.ssthresh + 3 * self.mss
        self.fast_recovery = True
        self.recovery_point = self.cwnd
        
    def exit_fast_recovery(self):
        """Exit fast recovery phase"""
        self.cwnd = self.ssthresh
        self.fast_recovery = False
        self.duplicate_acks = 0
        
    def get_send_window(self, advertised_window: int) -> int:
        """Get effective send window"""
        return min(int(self.cwnd), advertised_window)

class TCPTimerManager:
    """Manages all TCP timers using a heap"""
    
    def __init__(self):
        self.timers = []  # Heap of TCPTimer objects
        self.timer_callbacks = {}
        
    def add_timer(self, timer: TCPTimer, callback):
        """Add a timer with callback"""
        heapq.heappush(self.timers, timer)
        self.timer_callbacks[id(timer)] = callback
        
    def cancel_timers(self, timer_type: TCPTimerType, conn_id: Tuple):
        """Cancel all timers of specific type for connection"""
        new_timers = []
        for timer in self.timers:
            if not (timer.timer_type == timer_type and 
                   hasattr(timer.callback_data, 'conn_id') and 
                   timer.callback_data.conn_id == conn_id):
                new_timers.append(timer)
            else:
                # Remove callback
                if id(timer) in self.timer_callbacks:
                    del self.timer_callbacks[id(timer)]
        
        self.timers = new_timers
        heapq.heapify(self.timers)
        
    async def process_expired_timers(self):
        """Process all expired timers"""
        current_time = time.time()
        
        while self.timers and self.timers[0].expire_time <= current_time:
            timer = heapq.heappop(self.timers)
            callback = self.timer_callbacks.get(id(timer))
            
            if callback:
                try:
                    await callback(timer)
                except Exception as e:
                    logger.error(f"Timer callback error: {e}")
                    
                # Clean up callback
                del self.timer_callbacks[id(timer)]

@dataclass
class TCPConnection:
    """Enhanced TCP connection with full state tracking and RFC 793 compliance"""
    state: TCPState = TCPState.CLOSED
    local_sock: Optional[asyncio.StreamWriter] = None
    local_reader: Optional[asyncio.StreamReader] = None
    
    # Sequence numbers
    seq_num: int = 0
    ack_num: int = 0
    initial_seq: int = 0
    initial_ack: int = 0
    
    # Send sequence space (RFC 793)
    snd_una: int = 0  # Oldest unacknowledged sequence number
    snd_nxt: int = 0  # Next sequence number to send
    snd_wnd: int = 0  # Send window
    snd_wl1: int = 0  # Sequence number of last window update
    snd_wl2: int = 0  # Acknowledgment number of last window update
    
    # Receive sequence space
    rcv_nxt: int = 0  # Next sequence number expected
    rcv_wnd: int = 8192  # Receive window
    
    # Window management
    window_size: int = 8192
    max_window_size: int = 65535
    window_scale: int = 0  # Window scaling factor
    
    # Timing and RTT
    rtt_estimator: RTTEstimator = field(default_factory=RTTEstimator)
    last_activity: float = field(default_factory=time.time)
    
    # Congestion control
    congestion_control: CongestionControl = field(default_factory=CongestionControl)
    
    # Retransmission
    retransmit_queue: deque = field(default_factory=deque)
    retransmit_timer: Optional[TCPTimer] = None
    max_retransmit_count: int = 6
    
    # Out-of-order segments
    out_of_order_queue: List[TCPSegment] = field(default_factory=list)
    
    # TCP Options
    mss: int = 1460  # Maximum Segment Size
    peer_mss: int = 536  # Peer's MSS
    sack_permitted: bool = False
    timestamp_enabled: bool = False
    
    # Buffering
    send_buffer: bytes = b''
    recv_buffer: bytes = b''
    
    # Connection identifiers
    src_ip: bytes = b''
    dst_ip: bytes = b''
    src_port: int = 0
    dst_port: int = 0
    
    # Flow control
    bytes_in_flight: int = 0  # Bytes sent but not yet acknowledged
    
    # Keep-alive
    keepalive_enabled: bool = False
    keepalive_idle: int = 7200  # 2 hours
    keepalive_interval: int = 75
    keepalive_probes: int = 9
    
    def get_connection_id(self) -> Tuple[int, int, bytes, bytes]:
        """Get unique connection identifier"""
        return (self.src_port, self.dst_port, self.src_ip, self.dst_ip)
    
    def get_available_window(self) -> int:
        """Get available send window considering congestion and flow control"""
        advertised_window = self.snd_wnd
        congestion_window = int(self.congestion_control.cwnd)
        return min(advertised_window, congestion_window) - self.bytes_in_flight
    
    def can_send_data(self, data_len: int) -> bool:
        """Check if data can be sent considering window limits"""
        return data_len <= self.get_available_window()
    
    def add_to_retransmit_queue(self, segment: TCPSegment):
        """Add segment to retransmission queue"""
        self.retransmit_queue.append(segment)
        self.bytes_in_flight += len(segment.data)
    
    def remove_from_retransmit_queue(self, ack_num: int):
        """Remove acknowledged segments from retransmission queue"""
        bytes_acked = 0
        
        while self.retransmit_queue:
            segment = self.retransmit_queue[0]
            if segment.seq_end <= ack_num:
                self.retransmit_queue.popleft()
                bytes_acked += len(segment.data)
                self.bytes_in_flight -= len(segment.data)
            else:
                break
                
        if bytes_acked > 0:
            self.congestion_control.on_ack(bytes_acked)
            
        return bytes_acked
    
    def get_next_retransmit_segment(self) -> Optional[TCPSegment]:
        """Get next segment that needs retransmission"""
        if self.retransmit_queue:
            return self.retransmit_queue[0]
        return None

class TCPOptionsHandler:
    """Handles TCP option parsing and creation"""
    
    @staticmethod
    def parse_options(options_data: bytes) -> Dict[int, bytes]:
        """Parse TCP options from segment"""
        options = {}
        offset = 0
        
        while offset < len(options_data):
            if offset >= len(options_data):
                break
                
            option_type = options_data[offset]
            
            if option_type == TCPOption.END_OF_OPTION_LIST:
                break
            elif option_type == TCPOption.NO_OPERATION:
                offset += 1
                continue
            else:
                if offset + 1 >= len(options_data):
                    break
                    
                option_length = options_data[offset + 1]
                if option_length < 2 or offset + option_length > len(options_data):
                    break
                    
                option_data = options_data[offset + 2:offset + option_length]
                options[option_type] = option_data
                offset += option_length
                
        return options
    
    @staticmethod
    def build_options(options: Dict[int, bytes]) -> bytes:
        """Build TCP options data"""
        data = bytearray()
        
        for option_type, option_data in options.items():
            if option_type == TCPOption.NO_OPERATION:
                data.append(option_type)
            else:
                data.append(option_type)
                data.append(2 + len(option_data))
                data.extend(option_data)
        
        # Pad to 4-byte boundary
        while len(data) % 4 != 0:
            data.append(TCPOption.NO_OPERATION)
            
        return bytes(data)
    
    @staticmethod
    def create_mss_option(mss: int) -> bytes:
        """Create MSS option"""
        return struct.pack('!H', mss)
    
    @staticmethod
    def create_window_scale_option(scale: int) -> bytes:
        """Create window scale option"""
        return struct.pack('!B', scale)
    
    @staticmethod
    def create_sack_permitted_option() -> bytes:
        """Create SACK permitted option"""
        return b''
    
    @staticmethod
    def create_timestamp_option(ts_val: int, ts_ecr: int = 0) -> bytes:
        """Create timestamp option"""
        return struct.pack('!II', ts_val, ts_ecr)

class TCPStateMachine:
    """Complete RFC 793 compliant TCP state machine"""
    
    def __init__(self, timer_manager: TCPTimerManager):
        self.timer_manager = timer_manager
        self.options_handler = TCPOptionsHandler()
        
    async def process_segment(self, conn: TCPConnection, segment_info: Dict, 
                             tcp_stack, writer: asyncio.StreamWriter) -> Optional[bytes]:
        """Process TCP segment according to current connection state"""
        
        # Update last activity
        conn.last_activity = time.time()
        
        # Extract segment information
        seq = segment_info['seq']
        ack = segment_info['ack']
        flags = segment_info['flags']
        window = segment_info['window']
        data = segment_info['data']
        
        # Parse TCP options if present
        options = {}
        if 'options' in segment_info:
            options = self.options_handler.parse_options(segment_info['options'])
        
        # Process based on current state
        if conn.state == TCPState.CLOSED:
            return await self._handle_closed_state(conn, segment_info, tcp_stack)
            
        elif conn.state == TCPState.LISTEN:
            return await self._handle_listen_state(conn, segment_info, tcp_stack)
            
        elif conn.state == TCPState.SYN_SENT:
            return await self._handle_syn_sent_state(conn, segment_info, tcp_stack, options)
            
        elif conn.state == TCPState.SYN_RCVD:
            return await self._handle_syn_rcvd_state(conn, segment_info, tcp_stack)
            
        elif conn.state == TCPState.ESTABLISHED:
            logger.debug(f"TCP: Routing to ESTABLISHED state handler for {conn.src_port}->{conn.dst_port}")
            return await self._handle_established_state(conn, segment_info, tcp_stack, writer)
            
        elif conn.state == TCPState.FIN_WAIT_1:
            return await self._handle_fin_wait_1_state(conn, segment_info, tcp_stack)
            
        elif conn.state == TCPState.FIN_WAIT_2:
            return await self._handle_fin_wait_2_state(conn, segment_info, tcp_stack)
            
        elif conn.state == TCPState.CLOSE_WAIT:
            return await self._handle_close_wait_state(conn, segment_info, tcp_stack)
            
        elif conn.state == TCPState.CLOSING:
            return await self._handle_closing_state(conn, segment_info, tcp_stack)
            
        elif conn.state == TCPState.LAST_ACK:
            return await self._handle_last_ack_state(conn, segment_info, tcp_stack)
            
        elif conn.state == TCPState.TIME_WAIT:
            return await self._handle_time_wait_state(conn, segment_info, tcp_stack)
        
        return None
    
    async def _handle_closed_state(self, conn: TCPConnection, segment_info: Dict, tcp_stack) -> Optional[bytes]:
        """Handle segment in CLOSED state"""
        # Send RST for any incoming segment (except RST)
        if not (segment_info['flags'] & TCPFlags.RST):
            if segment_info['flags'] & TCPFlags.ACK:
                # RST with seq = ack_num
                return self._create_rst_segment(
                    tcp_stack, segment_info,
                    seq=segment_info['ack'], ack=0, flags=TCPFlags.RST
                )
            else:
                # RST+ACK with ack = seq + seg.len
                seg_len = len(segment_info['data'])
                if segment_info['flags'] & (TCPFlags.SYN | TCPFlags.FIN):
                    seg_len += 1
                    
                return self._create_rst_segment(
                    tcp_stack, segment_info,
                    seq=0, ack=segment_info['seq'] + seg_len,
                    flags=TCPFlags.RST | TCPFlags.ACK
                )
        return None
    
    async def _handle_listen_state(self, conn: TCPConnection, segment_info: Dict, tcp_stack) -> Optional[bytes]:
        """Handle segment in LISTEN state"""
        flags = segment_info['flags']
        
        # First check for RST
        if flags & TCPFlags.RST:
            return None  # Ignore RST in LISTEN state
            
        # Check for ACK - should be reset
        if flags & TCPFlags.ACK:
            return self._create_rst_segment(
                tcp_stack, segment_info,
                seq=segment_info['ack'], ack=0, flags=TCPFlags.RST
            )
        
        # Check for SYN
        if flags & TCPFlags.SYN:
            # Initialize connection
            conn.rcv_nxt = segment_info['seq'] + 1
            conn.initial_ack = segment_info['seq']
            conn.snd_nxt = conn.initial_seq + 1
            conn.snd_una = conn.initial_seq
            conn.state = TCPState.SYN_RCVD
            
            # Create SYN+ACK response
            response_flags = TCPFlags.SYN | TCPFlags.ACK
            options_data = self._build_syn_options(conn)
            
            logger.info(f"Creating SYN+ACK: {segment_info['dst_port']}->{segment_info['src_port']} seq={conn.initial_seq} ack={conn.rcv_nxt}")
            logger.debug(f"SYN+ACK Details: initial_seq={conn.initial_seq}, rcv_nxt={conn.rcv_nxt}, client_seq={segment_info['seq']}")
            
            tcp_segment = self._create_tcp_segment(
                tcp_stack, segment_info,
                seq=conn.initial_seq, ack=conn.rcv_nxt,
                flags=response_flags, options=options_data
            )
            
            # Create IP packet containing the TCP segment
            ip_packet = tcp_stack.create_ip_packet(
                segment_info['dst_ip'], segment_info['src_ip'],
                tcp_segment
            )
            
            logger.info(f"SYN+ACK IP packet created: {len(ip_packet)} bytes")
            
            # Set retransmission timer
            await self._set_retransmission_timer(conn, tcp_segment)
            
            return ip_packet
            
        return None
    
    async def _handle_syn_sent_state(self, conn: TCPConnection, segment_info: Dict, 
                                   tcp_stack, options: Dict) -> Optional[bytes]:
        """Handle segment in SYN_SENT state"""
        flags = segment_info['flags']
        seq = segment_info['seq']
        ack = segment_info['ack']
        
        # Check ACK first
        if flags & TCPFlags.ACK:
            if ack <= conn.snd_una or ack > conn.snd_nxt:
                # Unacceptable ACK
                if not (flags & TCPFlags.RST):
                    return self._create_rst_segment(
                        tcp_stack, segment_info,
                        seq=ack, ack=0, flags=TCPFlags.RST
                    )
                return None
        
        # Check RST
        if flags & TCPFlags.RST:
            if flags & TCPFlags.ACK:
                # Connection refused
                conn.state = TCPState.CLOSED
                # Signal error to application
            return None
        
        # Check SYN
        if flags & TCPFlags.SYN:
            conn.rcv_nxt = seq + 1
            
            if flags & TCPFlags.ACK:
                # SYN+ACK received
                conn.snd_una = ack
                
                # Process options
                await self._process_syn_options(conn, options)
                
                # Remove SYN from retransmission queue
                conn.remove_from_retransmit_queue(ack)
                
                conn.state = TCPState.ESTABLISHED
                
                # Send ACK
                return self._create_tcp_segment(
                    tcp_stack, segment_info,
                    seq=conn.snd_nxt, ack=conn.rcv_nxt,
                    flags=TCPFlags.ACK
                )
            else:
                # Simultaneous open - SYN received
                conn.state = TCPState.SYN_RCVD
                
                # Send SYN+ACK
                response_flags = TCPFlags.SYN | TCPFlags.ACK
                return self._create_tcp_segment(
                    tcp_stack, segment_info,
                    seq=conn.snd_nxt, ack=conn.rcv_nxt,
                    flags=response_flags
                )
        
        return None
    
    async def _handle_syn_rcvd_state(self, conn: TCPConnection, segment_info: Dict, tcp_stack) -> Optional[bytes]:
        """Handle segment in SYN_RCVD state"""
        flags = segment_info['flags']
        seq = segment_info['seq']
        ack = segment_info['ack']
        
        # Check sequence number
        is_seq_acceptable = self._is_sequence_acceptable(conn, seq, len(segment_info['data']))
        logger.debug(f"TCP: Sequence check - seq={seq}, rcv_nxt={conn.rcv_nxt}, acceptable={is_seq_acceptable}")
        if not is_seq_acceptable:
            logger.debug(f"TCP: Rejecting packet due to unacceptable sequence number")
            if not (flags & TCPFlags.RST):
                return self._create_ack_segment(tcp_stack, segment_info, conn)
            return None
        
        # Check RST
        if flags & TCPFlags.RST:
            conn.state = TCPState.LISTEN  # Return to LISTEN
            return None
        
        # Check ACK
        if flags & TCPFlags.ACK:
            logger.debug(f"TCP: ACK validation - snd_una={conn.snd_una}, ack={ack}, snd_nxt={conn.snd_nxt}")
            if conn.snd_una <= ack <= conn.snd_nxt:
                # Acceptable ACK
                logger.info(f"TCP: Connection {conn.src_port}->{conn.dst_port} transitioning to ESTABLISHED")
                conn.state = TCPState.ESTABLISHED
                conn.snd_una = ack
                
                # Remove acknowledged data from retransmission queue
                conn.remove_from_retransmit_queue(ack)
                
                # Process any data
                if segment_info['data']:
                    return await self._process_data_segment(conn, segment_info, tcp_stack)
                    
            else:
                # Unacceptable ACK
                logger.error(f"TCP: UNACCEPTABLE ACK - expected {conn.snd_una} <= {ack} <= {conn.snd_nxt}, sending RST")
                return self._create_rst_segment(
                    tcp_stack, segment_info,
                    seq=ack, ack=0, flags=TCPFlags.RST
                )
        
        return None
    
    async def _handle_established_state(self, conn: TCPConnection, segment_info: Dict, 
                                      tcp_stack, writer: asyncio.StreamWriter) -> Optional[bytes]:
        """Handle segment in ESTABLISHED state"""
        flags = segment_info['flags']
        seq = segment_info['seq']
        ack = segment_info['ack']
        data = segment_info['data']
        
        # Check sequence number
        if not self._is_sequence_acceptable(conn, seq, len(data)):
            if not (flags & TCPFlags.RST):
                return self._create_ack_segment(tcp_stack, segment_info, conn)
            return None
        
        # Check RST
        if flags & TCPFlags.RST:
            conn.state = TCPState.CLOSED
            # Signal connection reset to application
            return None
        
        # Process ACK
        if flags & TCPFlags.ACK:
            if conn.snd_una < ack <= conn.snd_nxt:
                # Acceptable ACK
                bytes_acked = conn.remove_from_retransmit_queue(ack)
                conn.snd_una = ack
                
                # Update RTT if this ACKs new data
                if bytes_acked > 0:
                    # Calculate RTT sample (simplified - would need timestamp tracking)
                    sample_rtt = time.time() - conn.last_activity
                    conn.rtt_estimator.update_rtt(sample_rtt)
                    
            elif ack > conn.snd_nxt:
                # ACK for unsent data
                return self._create_ack_segment(tcp_stack, segment_info, conn)
        
        # Process data using new bidirectional proxy pattern
        response = None
        logger.debug(f"TCP: Processing data - seq={seq}, rcv_nxt={conn.rcv_nxt}, data_len={len(data) if data else 0}")
        if data:
            logger.debug(f"TCP: Data packet - seq={seq}, expected_rcv_nxt={conn.rcv_nxt}, len={len(data)}")
            logger.debug(f"TCP: Data content preview: {data[:20]}")
            # Check if this is in-sequence data (most common case)
            if seq == conn.rcv_nxt:
                # Data in sequence
                logger.info(f"TCP: ESTABLISHED state - received {len(data)} bytes in sequence")
                conn.rcv_nxt += len(data)
                
                # Check if this is first data in ESTABLISHED state - establish bidirectional forwarding
                if not hasattr(conn, 'proxy_task') or conn.proxy_task is None:
                    logger.info(f"[SETUP] First data in ESTABLISHED state for {conn.src_port}->{conn.dst_port} - establishing bidirectional forwarding")
                    logger.info(f"[SETUP] Data content: {data[:50]} (showing first 50 bytes)")
                    
                    # Map destination port to service
                    service_port = tcp_stack._map_service_port(conn.dst_port)
                    success = await tcp_stack.proxy.establish_bidirectional_forwarding(
                        conn, "127.0.0.1", service_port, writer
                    )
                    
                    if not success:
                        # Forwarding failed, close connection
                        logger.error("Failed to establish bidirectional forwarding, closing connection")
                        conn.state = TCPState.CLOSED
                        return self._create_rst_segment(
                            tcp_stack, segment_info,
                            seq=conn.snd_nxt, ack=conn.rcv_nxt, flags=TCPFlags.RST
                        )
                
                # Queue data for bidirectional forwarding instead of forwarding directly
                logger.info(f"[DATA] Queueing {len(data)} bytes for forwarding to service: {data[:20]}")
                await tcp_stack.proxy.handle_ppp_data(conn, data)
                
                # Check for out-of-order segments that can now be processed
                await self._process_out_of_order_queue(conn, writer)
                
                # Send ACK (non-blocking)
                response = self._create_ack_segment(tcp_stack, segment_info, conn)
            elif seq < conn.rcv_nxt:
                # Data we've already received (retransmission or overlap)
                logger.debug(f"TCP: Retransmitted or overlapping data - seq={seq}, rcv_nxt={conn.rcv_nxt}, treating as acceptable")
                overlap_start = max(0, conn.rcv_nxt - seq)
                new_data = data[overlap_start:]
                if new_data:
                    logger.info(f"TCP: ESTABLISHED state - processing {len(new_data)} bytes of new data from retransmission")
                    conn.rcv_nxt += len(new_data)
                    
                    # Check if this is first data in ESTABLISHED state - establish bidirectional forwarding
                    if not hasattr(conn, 'proxy_task') or conn.proxy_task is None:
                        logger.info(f"[SETUP] First data in ESTABLISHED state for {conn.src_port}->{conn.dst_port} - establishing bidirectional forwarding")
                        logger.info(f"[SETUP] Data content: {new_data[:50]} (showing first 50 bytes)")
                        
                        # Map destination port to service
                        service_port = tcp_stack._map_service_port(conn.dst_port)
                        success = await tcp_stack.proxy.establish_bidirectional_forwarding(
                            conn, "127.0.0.1", service_port, writer
                        )
                        
                        if not success:
                            # Forwarding failed, close connection
                            logger.error("Failed to establish bidirectional forwarding, closing connection")
                            conn.state = TCPState.CLOSED
                            return self._create_rst_segment(
                                tcp_stack, segment_info,
                                seq=conn.snd_nxt, ack=conn.rcv_nxt, flags=TCPFlags.RST
                            )
                        
                        # Queue data for bidirectional forwarding instead of forwarding directly
                        logger.info(f"[DATA] Queueing {len(new_data)} bytes for forwarding to service: {new_data[:20]}")
                        await tcp_stack.proxy.handle_ppp_data(conn, new_data)
                        
                        # Check for out-of-order segments that can now be processed
                        await self._process_out_of_order_queue(conn, writer)
                        
                        # Send ACK (non-blocking)
                        response = self._create_ack_segment(tcp_stack, segment_info, conn)
                    else:
                        # Forwarding already established, just forward the new data
                        logger.info(f"[DATA] Queueing {len(new_data)} bytes for forwarding to service: {new_data[:20]}")
                        await tcp_stack.proxy.handle_ppp_data(conn, new_data)
                        response = self._create_ack_segment(tcp_stack, segment_info, conn)
                else:
                    logger.debug(f"TCP: No new data in retransmission, just ACKing")
                    response = self._create_ack_segment(tcp_stack, segment_info, conn)
            else:
                # Out of sequence data (future data)
                logger.debug(f"TCP: Out of sequence data - expected seq {conn.rcv_nxt}, got {seq}, queueing")
                self._queue_out_of_order_segment(conn, seq, data)
                # Send duplicate ACK
                response = self._create_ack_segment(tcp_stack, segment_info, conn)
        else:
            logger.debug(f"TCP: No data in packet - seq={seq}, rcv_nxt={conn.rcv_nxt}, flags=0x{flags:02x}")
        
        # Check FIN
        if flags & TCPFlags.FIN:
            conn.rcv_nxt += 1  # FIN consumes sequence number
            # Signal bidirectional forwarding to stop
            if hasattr(conn, '_shutdown_event') and conn._shutdown_event:
                conn._shutdown_event.set()
            conn.state = TCPState.CLOSE_WAIT
            
            # Send ACK for FIN
            return self._create_ack_segment(tcp_stack, segment_info, conn)
        
        return response
    
    async def _handle_fin_wait_1_state(self, conn: TCPConnection, segment_info: Dict, tcp_stack) -> Optional[bytes]:
        """Handle segment in FIN_WAIT_1 state"""
        flags = segment_info['flags']
        ack = segment_info['ack']
        
        # Process ACK
        if flags & TCPFlags.ACK:
            if ack == conn.snd_nxt:  # ACK for our FIN
                conn.state = TCPState.FIN_WAIT_2
                conn.snd_una = ack
        
        # Check FIN
        if flags & TCPFlags.FIN:
            conn.rcv_nxt += 1
            
            if conn.state == TCPState.FIN_WAIT_2:
                # Simultaneous close
                conn.state = TCPState.TIME_WAIT
                await self._set_time_wait_timer(conn)
            else:
                # FIN received before ACK of our FIN
                conn.state = TCPState.CLOSING
            
            return self._create_ack_segment(tcp_stack, segment_info, conn)
        
        return None
    
    async def _handle_fin_wait_2_state(self, conn: TCPConnection, segment_info: Dict, tcp_stack) -> Optional[bytes]:
        """Handle segment in FIN_WAIT_2 state"""
        flags = segment_info['flags']
        
        # Check FIN
        if flags & TCPFlags.FIN:
            conn.rcv_nxt += 1
            conn.state = TCPState.TIME_WAIT
            await self._set_time_wait_timer(conn)
            
            return self._create_ack_segment(tcp_stack, segment_info, conn)
        
        return None
    
    async def _handle_close_wait_state(self, conn: TCPConnection, segment_info: Dict, tcp_stack) -> Optional[bytes]:
        """Handle segment in CLOSE_WAIT state"""
        # Process normally (like ESTABLISHED) but don't accept new data
        # Application should close when ready
        return None
    
    async def _handle_closing_state(self, conn: TCPConnection, segment_info: Dict, tcp_stack) -> Optional[bytes]:
        """Handle segment in CLOSING state"""
        flags = segment_info['flags']
        ack = segment_info['ack']
        
        # Check ACK for our FIN
        if flags & TCPFlags.ACK and ack == conn.snd_nxt:
            conn.state = TCPState.TIME_WAIT
            await self._set_time_wait_timer(conn)
        
        return None
    
    async def _handle_last_ack_state(self, conn: TCPConnection, segment_info: Dict, tcp_stack) -> Optional[bytes]:
        """Handle segment in LAST_ACK state"""
        flags = segment_info['flags']
        ack = segment_info['ack']
        
        # Check ACK for our FIN
        if flags & TCPFlags.ACK and ack == conn.snd_nxt:
            conn.state = TCPState.CLOSED
            # Connection can be deleted
        
        return None
    
    async def _handle_time_wait_state(self, conn: TCPConnection, segment_info: Dict, tcp_stack) -> Optional[bytes]:
        """Handle segment in TIME_WAIT state"""
        # Restart TIME_WAIT timer if segment received
        await self._set_time_wait_timer(conn)
        return None
    
    # Helper methods
    
    def _is_sequence_acceptable(self, conn: TCPConnection, seq: int, seg_len: int) -> bool:
        """Check if sequence number is acceptable (RFC 793)"""
        rcv_wnd = conn.rcv_wnd
        rcv_nxt = conn.rcv_nxt
        
        if seg_len == 0:
            if rcv_wnd == 0:
                return seq == rcv_nxt
            else:
                return rcv_nxt <= seq < rcv_nxt + rcv_wnd
        else:
            if rcv_wnd == 0:
                return False
            else:
                return (rcv_nxt <= seq < rcv_nxt + rcv_wnd) or \
                       (rcv_nxt <= seq + seg_len - 1 < rcv_nxt + rcv_wnd)
    
    def _create_tcp_segment(self, tcp_stack, segment_info: Dict, 
                           seq: int, ack: int, flags: int, 
                           data: bytes = b'', options: bytes = b'') -> bytes:
        """Create TCP segment"""
        return tcp_stack.create_tcp_segment(
            segment_info['dst_ip'], segment_info['src_ip'],
            segment_info['dst_port'], segment_info['src_port'],
            seq, ack, flags, data=data, options=options
        )
    
    def _create_rst_segment(self, tcp_stack, segment_info: Dict, 
                           seq: int, ack: int, flags: int) -> bytes:
        """Create RST segment"""
        tcp_seg = self._create_tcp_segment(tcp_stack, segment_info, seq, ack, flags)
        return tcp_stack.create_ip_packet(
            segment_info['dst_ip'], segment_info['src_ip'], tcp_seg
        )
    
    def _create_ack_segment(self, tcp_stack, segment_info: Dict, conn: TCPConnection) -> bytes:
        """Create ACK segment"""
        # Update ack_num to match rcv_nxt for proper acknowledgment
        conn.ack_num = conn.rcv_nxt
        tcp_seg = self._create_tcp_segment(
            tcp_stack, segment_info,
            conn.snd_nxt, conn.rcv_nxt, TCPFlags.ACK
        )
        return tcp_stack.create_ip_packet(
            segment_info['dst_ip'], segment_info['src_ip'], tcp_seg
        )
    
    def _build_syn_options(self, conn: TCPConnection) -> bytes:
        """Build SYN options"""
        options = {
            TCPOption.MSS: self.options_handler.create_mss_option(conn.mss)
        }
        return self.options_handler.build_options(options)
    
    async def _process_syn_options(self, conn: TCPConnection, options: Dict):
        """Process options from SYN segment"""
        if TCPOption.MSS in options:
            mss_data = options[TCPOption.MSS]
            if len(mss_data) == 2:
                conn.peer_mss = struct.unpack('!H', mss_data)[0]
                # Update congestion control with peer MSS
                conn.congestion_control.mss = min(conn.mss, conn.peer_mss)
    
    async def _process_data_segment(self, conn: TCPConnection, segment_info: Dict, tcp_stack) -> Optional[bytes]:
        """Process data in segment"""
        data = segment_info['data']
        if data:
            logger.info(f"TCP: Received {len(data)} bytes of data from PPP client, forwarding to service")
            conn.rcv_nxt += len(data)
            
            # Forward data to local service
            if conn.local_sock:
                try:
                    conn.local_sock.write(data)
                    await conn.local_sock.drain()
                    logger.info(f"TCP: Successfully forwarded {len(data)} bytes to local service")
                except Exception as e:
                    logger.error(f"TCP: Failed to forward data to local service: {e}")
            else:
                logger.warning(f"TCP: No local service socket available to forward {len(data)} bytes")
                # Buffer the data for when service becomes available
                if not hasattr(conn, 'send_buffer'):
                    conn.send_buffer = b''
                conn.send_buffer += data
            
        return self._create_ack_segment(tcp_stack, segment_info, conn)
    
    def _queue_out_of_order_segment(self, conn: TCPConnection, seq: int, data: bytes):
        """Queue out-of-order segment"""
        segment = TCPSegment(seq, seq + len(data), data, 0, time.time())
        
        # Insert in order
        inserted = False
        for i, existing in enumerate(conn.out_of_order_queue):
            if seq < existing.seq_start:
                conn.out_of_order_queue.insert(i, segment)
                inserted = True
                break
        
        if not inserted:
            conn.out_of_order_queue.append(segment)
    
    async def _process_out_of_order_queue(self, conn: TCPConnection, writer: asyncio.StreamWriter):
        """Process queued out-of-order segments"""
        while conn.out_of_order_queue:
            segment = conn.out_of_order_queue[0]
            if segment.seq_start == conn.rcv_nxt:
                # This segment can be processed now
                conn.out_of_order_queue.pop(0)
                conn.rcv_nxt = segment.seq_end
                
                # Forward data to local socket
                if conn.local_sock and segment.data:
                    conn.local_sock.write(segment.data)
                    await conn.local_sock.drain()
            else:
                break
    
    async def _set_retransmission_timer(self, conn: TCPConnection, segment: bytes):
        """Set retransmission timer for segment"""
        timer = TCPTimer(
            TCPTimerType.RETRANSMISSION,
            time.time() + conn.rtt_estimator.get_rto(),
            {'conn_id': conn.get_connection_id(), 'segment': segment}
        )
        
        async def retransmit_callback(timer: TCPTimer):
            # Retransmit segment
            logger.debug(f"Retransmitting segment for {timer.callback_data['conn_id']}")
            # Would need reference to writer to actually retransmit
            
        self.timer_manager.add_timer(timer, retransmit_callback)
    
    async def _set_time_wait_timer(self, conn: TCPConnection):
        """Set TIME_WAIT timer (2*MSL)"""
        timer = TCPTimer(
            TCPTimerType.TIME_WAIT,
            time.time() + 240.0,  # 2*MSL = 4 minutes
            {'conn_id': conn.get_connection_id()}
        )
        
        async def time_wait_callback(timer: TCPTimer):
            # Close connection
            logger.debug(f"TIME_WAIT expired for {timer.callback_data['conn_id']}")
            conn.state = TCPState.CLOSED
            
        self.timer_manager.add_timer(timer, time_wait_callback)
    
    def _map_service_port(self, ppp_port: int) -> int:
        """Map PPP destination port to actual service port"""
        port_mapping = {
            22: 22,      # SSH
            80: 80,      # HTTP
            443: 443,    # HTTPS
            8888: 8888,  # Echo server for testing
        }
        return port_mapping.get(ppp_port, ppp_port)

class AsyncPPPHandler:
    """Async PPP frame handler"""
    
    def __init__(self):
        self.buffer = bytearray()
        self.in_frame = False
        self.escaped = False
    
    async def process_data(self, data: bytes) -> list:
        """Process incoming data and return list of complete frames"""
        frames = []
        
        for byte in data:
            if byte == 0x7E:  # PPP_FLAG
                if self.in_frame and len(self.buffer) > 0:
                    frames.append(bytes(self.buffer))
                    self.buffer.clear()
                    self.in_frame = False
                else:
                    self.in_frame = True
                    self.buffer.clear()
                    self.escaped = False
            elif self.in_frame:
                if byte == 0x7D:  # PPP_ESCAPE
                    self.escaped = True
                elif self.escaped:
                    self.buffer.append(byte ^ 0x20)
                    self.escaped = False
                else:
                    self.buffer.append(byte)
        
        return frames
    
    @staticmethod
    def frame_data(data: bytes) -> bytes:
        """Add PPP framing to data"""
        result = bytearray([0x7E])  # Start flag
        
        for byte in data:
            if byte in (0x7E, 0x7D):  # Flag or escape char
                result.append(0x7D)
                result.append(byte ^ 0x20)
            else:
                result.append(byte)
        
        result.append(0x7E)  # End flag
        return bytes(result)

class AsyncPPPNegotiator:
    """Complete PPP LCP/IPCP negotiation implementation (RFC 1661/1332)"""
    
    def __init__(self, local_ip="10.0.0.1", remote_ip="10.0.0.2", is_server=True):
        # State tracking
        self.lcp_state = PPPState.INITIAL
        self.ipcp_state = PPPState.INITIAL
        
        # Configuration
        self.local_ip = socket.inet_aton(local_ip)
        self.remote_ip = socket.inet_aton(remote_ip)
        self.magic_number = random.randint(1, 0xFFFFFFFF)
        self.peer_magic_number = 0
        self.mru = 1500
        self.peer_mru = 1500
        self.is_server = is_server  # Server waits, client initiates
        
        # Protocol state
        self.lcp_identifier = 0
        self.ipcp_identifier = 0
        self.restart_counter = 0
        self.max_configure = 10
        self.max_terminate = 2
        
        # Timers
        self.echo_interval = 30.0
        self.last_echo_time = 0.0
        self.restart_timer = 3.0
        self.negotiation_timeout = 10.0  # Timeout for initial negotiation
        self.negotiation_start_time = 0.0
        
        # Event tracking
        self.awaiting_response = {}
        self.peer_options = {}
        self.negotiation_initiated = False
        
        role = "Server" if is_server else "Client"
        logger.info(f"PPP Negotiator initialized [{role}] - Local: {local_ip}, Remote: {remote_ip}")
        logger.info(f"Magic Number: 0x{self.magic_number:08X}")
    
    def get_next_identifier(self, protocol: str) -> int:
        """Get next identifier for protocol"""
        if protocol == 'lcp':
            self.lcp_identifier = (self.lcp_identifier + 1) % 256
            return self.lcp_identifier
        elif protocol == 'ipcp':
            self.ipcp_identifier = (self.ipcp_identifier + 1) % 256
            return self.ipcp_identifier
        return 0
    
    def parse_config_options(self, data: bytes) -> List[PPPConfigOption]:
        """Parse configuration options from packet data"""
        options = []
        offset = 0
        
        while offset + 2 <= len(data):
            opt_type = data[offset]
            opt_length = data[offset + 1]
            
            if opt_length < 2 or offset + opt_length > len(data):
                logger.warning(f"Invalid option length: {opt_length}")
                break
            
            opt_data = data[offset + 2:offset + opt_length]
            options.append(PPPConfigOption(opt_type, opt_length, opt_data))
            offset += opt_length
        
        return options
    
    def build_config_options(self, options: List[PPPConfigOption]) -> bytes:
        """Build configuration options into packet data"""
        data = bytearray()
        for opt in options:
            data.append(opt.type)
            data.append(opt.length)
            data.extend(opt.data)
        return bytes(data)
    
    def create_ppp_packet(self, protocol: int, code: int, identifier: int, data: bytes = b'') -> bytes:
        """Create a complete PPP packet"""
        # Create control protocol packet
        packet_length = 4 + len(data)
        packet = struct.pack('!BBH', code, identifier, packet_length) + data
        
        # Add PPP header
        ppp_header = struct.pack('!BBH', 0xFF, 0x03, protocol)
        return ppp_header + packet
    
    def parse_ppp_packet(self, frame: bytes) -> Optional[Tuple[int, PPPPacket]]:
        """Parse PPP frame into protocol and packet"""
        if len(frame) < 8:  # Minimum: PPP header (4) + packet header (4)
            return None
        
        # Parse PPP header
        addr, control, protocol = struct.unpack('!BBH', frame[:4])
        
        if addr != 0xFF or control != 0x03:
            logger.warning(f"Invalid PPP header: addr=0x{addr:02X}, control=0x{control:02X}")
            return None
        
        # Parse control protocol packet
        packet_data = frame[4:]
        if len(packet_data) < 4:
            return None
        
        code, identifier, length = struct.unpack('!BBH', packet_data[:4])
        
        if length < 4 or length > len(packet_data):
            logger.warning(f"Invalid packet length: {length}")
            return None
        
        data = packet_data[4:length]
        packet = PPPPacket(code, identifier, length, data)
        
        return protocol, packet
    
    async def send_lcp_configure_request(self, writer: asyncio.StreamWriter) -> bytes:
        """Send LCP Configure-Request"""
        options = []
        
        # Magic Number option
        magic_data = struct.pack('!I', self.magic_number)
        options.append(PPPConfigOption(LCPOption.MAGIC_NUMBER, 6, magic_data))
        
        # MRU option
        mru_data = struct.pack('!H', self.mru)
        options.append(PPPConfigOption(LCPOption.MRU, 4, mru_data))
        
        # Address/Control Field Compression
        options.append(PPPConfigOption(LCPOption.ADDR_CONTROL_COMPRESSION, 2, b''))
        
        # Protocol Field Compression
        options.append(PPPConfigOption(LCPOption.PROTOCOL_COMPRESSION, 2, b''))
        
        identifier = self.get_next_identifier('lcp')
        data = self.build_config_options(options)
        
        packet = self.create_ppp_packet(PPPProtocol.LCP, PPPCode.CONFIGURE_REQUEST, identifier, data)
        
        self.lcp_state = PPPState.REQUEST_SENT
        self.awaiting_response[f'lcp_{identifier}'] = time.time()
        
        logger.debug(f"Sending LCP Configure-Request (ID: {identifier})")
        return packet
    
    async def handle_lcp_configure_request(self, packet: PPPPacket, writer: asyncio.StreamWriter = None) -> bytes:
        """Handle LCP Configure-Request"""
        # If we're a server and haven't initiated negotiation yet, do so now
        if self.is_server and not self.negotiation_initiated and self.lcp_state == PPPState.STARTING:
            self.negotiation_initiated = True
            logger.info("Server received initial LCP Configure-Request from client")
            # Send our own Configure-Request in response
            if writer:
                lcp_request = await self.send_lcp_configure_request(writer)
                framed = AsyncPPPHandler.frame_data(lcp_request)
                writer.write(framed)
                await writer.drain()
        
        options = self.parse_config_options(packet.data)
        response_options = []
        response_code = PPPCode.CONFIGURE_ACK
        
        for opt in options:
            if opt.type == LCPOption.MAGIC_NUMBER:
                if len(opt.data) == 4:
                    peer_magic = struct.unpack('!I', opt.data)[0]
                    self.peer_magic_number = peer_magic
                    if peer_magic == self.magic_number:
                        # Magic number conflict - NAK with different value
                        response_code = PPPCode.CONFIGURE_NAK
                        new_magic = struct.pack('!I', random.randint(1, 0xFFFFFFFF))
                        response_options.append(PPPConfigOption(opt.type, opt.length, new_magic))
                        logger.warning("Magic number conflict detected")
                    else:
                        response_options.append(opt)
                        logger.debug(f"Peer magic number: 0x{peer_magic:08X}")
                else:
                    response_code = PPPCode.CONFIGURE_REJECT
                    response_options.append(opt)
            
            elif opt.type == LCPOption.MRU:
                if len(opt.data) == 2:
                    peer_mru = struct.unpack('!H', opt.data)[0]
                    if peer_mru >= 68:  # Minimum MRU
                        self.peer_mru = peer_mru
                        response_options.append(opt)
                        logger.debug(f"Peer MRU: {peer_mru}")
                    else:
                        response_code = PPPCode.CONFIGURE_NAK
                        nak_mru = struct.pack('!H', 1500)
                        response_options.append(PPPConfigOption(opt.type, opt.length, nak_mru))
                else:
                    response_code = PPPCode.CONFIGURE_REJECT
                    response_options.append(opt)
            
            elif opt.type in [LCPOption.ADDR_CONTROL_COMPRESSION, LCPOption.PROTOCOL_COMPRESSION]:
                # Accept compression options
                response_options.append(opt)
            
            elif opt.type == LCPOption.AUTH_PROTOCOL:
                # Reject authentication for now
                response_code = PPPCode.CONFIGURE_REJECT
                response_options.append(opt)
                logger.debug("Authentication protocol rejected")
            
            else:
                # Unknown option - reject
                response_code = PPPCode.CONFIGURE_REJECT
                response_options.append(opt)
                logger.debug(f"Unknown LCP option: {opt.type}")
        
        # Update state based on response
        if response_code == PPPCode.CONFIGURE_ACK:
            if self.lcp_state == PPPState.REQUEST_SENT:
                self.lcp_state = PPPState.ACK_SENT
            elif self.lcp_state == PPPState.ACK_RECEIVED:
                self.lcp_state = PPPState.OPENED
                logger.info("LCP negotiation completed - Link established")
        
        data = self.build_config_options(response_options) if response_options else b''
        return self.create_ppp_packet(PPPProtocol.LCP, response_code, packet.identifier, data)
    
    async def handle_lcp_configure_ack(self, packet: PPPPacket):
        """Handle LCP Configure-Ack"""
        key = f'lcp_{packet.identifier}'
        if key in self.awaiting_response:
            del self.awaiting_response[key]
            
            if self.lcp_state == PPPState.REQUEST_SENT:
                self.lcp_state = PPPState.ACK_RECEIVED
            elif self.lcp_state == PPPState.ACK_SENT:
                self.lcp_state = PPPState.OPENED
                logger.info("LCP negotiation completed - Link established")
            
            logger.debug(f"LCP Configure-Ack received (ID: {packet.identifier})")
    
    async def handle_lcp_configure_nak(self, packet: PPPPacket) -> Optional[bytes]:
        """Handle LCP Configure-Nak"""
        key = f'lcp_{packet.identifier}'
        if key in self.awaiting_response:
            del self.awaiting_response[key]
            
            # Process NAK options and retry
            options = self.parse_config_options(packet.data)
            for opt in options:
                if opt.type == LCPOption.MAGIC_NUMBER and len(opt.data) == 4:
                    # Use suggested magic number
                    suggested_magic = struct.unpack('!I', opt.data)[0]
                    self.magic_number = suggested_magic
                    logger.debug(f"Updated magic number to: 0x{self.magic_number:08X}")
                elif opt.type == LCPOption.MRU and len(opt.data) == 2:
                    # Use suggested MRU
                    suggested_mru = struct.unpack('!H', opt.data)[0]
                    self.mru = suggested_mru
                    logger.debug(f"Updated MRU to: {self.mru}")
            
            logger.debug(f"LCP Configure-Nak received (ID: {packet.identifier}) - retrying")
            # Return new Configure-Request
            return None  # Will trigger retry in main handler
    
    async def send_lcp_echo_request(self, writer: asyncio.StreamWriter) -> bytes:
        """Send LCP Echo-Request for keepalive"""
        identifier = self.get_next_identifier('lcp')
        magic_data = struct.pack('!I', self.magic_number)
        
        packet = self.create_ppp_packet(PPPProtocol.LCP, PPPCode.ECHO_REQUEST, identifier, magic_data)
        
        self.last_echo_time = time.time()
        logger.debug(f"Sending LCP Echo-Request (ID: {identifier})")
        return packet
    
    async def handle_lcp_echo_request(self, packet: PPPPacket) -> bytes:
        """Handle LCP Echo-Request"""
        # Echo back with our magic number
        magic_data = struct.pack('!I', self.magic_number)
        response = self.create_ppp_packet(PPPProtocol.LCP, PPPCode.ECHO_REPLY, packet.identifier, magic_data)
        
        logger.debug(f"Sending LCP Echo-Reply (ID: {packet.identifier})")
        return response
    
    async def handle_lcp_echo_reply(self, packet: PPPPacket):
        """Handle LCP Echo-Reply"""
        if len(packet.data) >= 4:
            peer_magic = struct.unpack('!I', packet.data[:4])[0]
            if peer_magic != self.peer_magic_number:
                logger.warning(f"Echo-Reply magic mismatch: expected 0x{self.peer_magic_number:08X}, got 0x{peer_magic:08X}")
        
        logger.debug(f"LCP Echo-Reply received (ID: {packet.identifier})")
    
    def is_lcp_opened(self) -> bool:
        """Check if LCP is in opened state"""
        return self.lcp_state == PPPState.OPENED
    
    def is_ipcp_opened(self) -> bool:
        """Check if IPCP is in opened state"""
        return self.ipcp_state == PPPState.OPENED
    
    def is_ready_for_ip(self) -> bool:
        """Check if ready for IP traffic"""
        return self.is_lcp_opened() and self.is_ipcp_opened()
    
    async def needs_echo(self) -> bool:
        """Check if echo request should be sent"""
        return (self.is_lcp_opened() and 
                time.time() - self.last_echo_time > self.echo_interval)
    
    # IPCP Methods
    
    async def send_ipcp_configure_request(self, writer: asyncio.StreamWriter) -> bytes:
        """Send IPCP Configure-Request"""
        options = []
        
        # IP Address option - request our IP
        options.append(PPPConfigOption(IPCPOption.IP_ADDRESS, 6, self.local_ip))
        
        identifier = self.get_next_identifier('ipcp')
        data = self.build_config_options(options)
        
        packet = self.create_ppp_packet(PPPProtocol.IPCP, PPPCode.CONFIGURE_REQUEST, identifier, data)
        
        self.ipcp_state = PPPState.REQUEST_SENT
        self.awaiting_response[f'ipcp_{identifier}'] = time.time()
        
        logger.debug(f"Sending IPCP Configure-Request (ID: {identifier}) - IP: {socket.inet_ntoa(self.local_ip)}")
        return packet
    
    async def handle_ipcp_configure_request(self, packet: PPPPacket) -> bytes:
        """Handle IPCP Configure-Request"""
        options = self.parse_config_options(packet.data)
        response_options = []
        response_code = PPPCode.CONFIGURE_ACK
        
        for opt in options:
            if opt.type == IPCPOption.IP_ADDRESS:
                if len(opt.data) == 4:
                    requested_ip = opt.data
                    requested_ip_str = socket.inet_ntoa(requested_ip)
                    
                    # Check if requested IP is acceptable
                    if requested_ip == self.remote_ip:
                        # Client is requesting the correct IP
                        response_options.append(opt)
                        logger.debug(f"Peer IP address accepted: {requested_ip_str}")
                    else:
                        # NAK with correct IP
                        response_code = PPPCode.CONFIGURE_NAK
                        response_options.append(PPPConfigOption(opt.type, opt.length, self.remote_ip))
                        logger.debug(f"Peer IP address NAKed: {requested_ip_str} -> {socket.inet_ntoa(self.remote_ip)}")
                else:
                    response_code = PPPCode.CONFIGURE_REJECT
                    response_options.append(opt)
            
            elif opt.type in [IPCPOption.PRIMARY_DNS, IPCPOption.SECONDARY_DNS]:
                # Reject DNS options for now
                response_code = PPPCode.CONFIGURE_REJECT
                response_options.append(opt)
                logger.debug(f"DNS option rejected: {opt.type}")
            
            elif opt.type == IPCPOption.IP_COMPRESSION:
                # Reject IP compression for simplicity
                response_code = PPPCode.CONFIGURE_REJECT
                response_options.append(opt)
                logger.debug("IP compression rejected")
            
            else:
                # Unknown option - reject
                response_code = PPPCode.CONFIGURE_REJECT
                response_options.append(opt)
                logger.debug(f"Unknown IPCP option: {opt.type}")
        
        # Update state based on response
        if response_code == PPPCode.CONFIGURE_ACK:
            if self.ipcp_state == PPPState.REQUEST_SENT:
                self.ipcp_state = PPPState.ACK_SENT
            elif self.ipcp_state == PPPState.ACK_RECEIVED:
                self.ipcp_state = PPPState.OPENED
                logger.info("IPCP negotiation completed - IP layer ready")
        
        data = self.build_config_options(response_options) if response_options else b''
        return self.create_ppp_packet(PPPProtocol.IPCP, response_code, packet.identifier, data)
    
    async def handle_ipcp_configure_ack(self, packet: PPPPacket):
        """Handle IPCP Configure-Ack"""
        key = f'ipcp_{packet.identifier}'
        if key in self.awaiting_response:
            del self.awaiting_response[key]
            
            if self.ipcp_state == PPPState.REQUEST_SENT:
                self.ipcp_state = PPPState.ACK_RECEIVED
            elif self.ipcp_state == PPPState.ACK_SENT:
                self.ipcp_state = PPPState.OPENED
                logger.info("IPCP negotiation completed - IP layer ready")
            
            logger.debug(f"IPCP Configure-Ack received (ID: {packet.identifier})")
    
    async def handle_ipcp_configure_nak(self, packet: PPPPacket) -> Optional[bytes]:
        """Handle IPCP Configure-Nak"""
        key = f'ipcp_{packet.identifier}'
        if key in self.awaiting_response:
            del self.awaiting_response[key]
            
            # Process NAK options
            options = self.parse_config_options(packet.data)
            for opt in options:
                if opt.type == IPCPOption.IP_ADDRESS and len(opt.data) == 4:
                    # Peer suggests different IP for us
                    suggested_ip = opt.data
                    suggested_ip_str = socket.inet_ntoa(suggested_ip)
                    logger.debug(f"Peer suggests IP: {suggested_ip_str}")
                    # For now, keep our IP - could implement IP negotiation here
            
            logger.debug(f"IPCP Configure-Nak received (ID: {packet.identifier}) - retrying")
            return None  # Will trigger retry in main handler
    
    async def handle_ipcp_configure_reject(self, packet: PPPPacket) -> Optional[bytes]:
        """Handle IPCP Configure-Reject"""
        key = f'ipcp_{packet.identifier}'
        if key in self.awaiting_response:
            del self.awaiting_response[key]
            
            # Remove rejected options and retry
            rejected_options = self.parse_config_options(packet.data)
            logger.debug(f"IPCP Configure-Reject received (ID: {packet.identifier}) - options: {[opt.type for opt in rejected_options]}")
            
            return None  # Will trigger retry without rejected options
    
    # Main protocol handling method
    
    async def handle_ppp_packet(self, frame: bytes, writer: asyncio.StreamWriter) -> Optional[bytes]:
        """Handle incoming PPP control protocol packet"""
        parsed = self.parse_ppp_packet(frame)
        if not parsed:
            return None
        
        protocol, packet = parsed
        
        if protocol == PPPProtocol.LCP:
            return await self.handle_lcp_packet(packet, writer)
        elif protocol == PPPProtocol.IPCP:
            return await self.handle_ipcp_packet(packet, writer)
        else:
            logger.debug(f"Unsupported protocol: 0x{protocol:04X}")
            return None
    
    async def handle_lcp_packet(self, packet: PPPPacket, writer: asyncio.StreamWriter) -> Optional[bytes]:
        """Handle LCP packet"""
        if packet.code == PPPCode.CONFIGURE_REQUEST:
            return await self.handle_lcp_configure_request(packet, writer)
        elif packet.code == PPPCode.CONFIGURE_ACK:
            await self.handle_lcp_configure_ack(packet)
            
            # Start IPCP if LCP is now opened
            if self.is_lcp_opened() and self.ipcp_state == PPPState.INITIAL:
                logger.debug("LCP opened - starting IPCP negotiation")
                ipcp_request = await self.send_ipcp_configure_request(writer)
                framed = AsyncPPPHandler.frame_data(ipcp_request)
                writer.write(framed)
                await writer.drain()
            
        elif packet.code == PPPCode.CONFIGURE_NAK:
            result = await self.handle_lcp_configure_nak(packet)
            if result is None:  # Need to retry
                retry_request = await self.send_lcp_configure_request(writer)
                framed = AsyncPPPHandler.frame_data(retry_request)
                writer.write(framed)
                await writer.drain()
        
        elif packet.code == PPPCode.ECHO_REQUEST:
            return await self.handle_lcp_echo_request(packet)
        elif packet.code == PPPCode.ECHO_REPLY:
            await self.handle_lcp_echo_reply(packet)
        
        else:
            logger.debug(f"Unsupported LCP code: {packet.code}")
        
        return None
    
    async def handle_ipcp_packet(self, packet: PPPPacket, writer: asyncio.StreamWriter) -> Optional[bytes]:
        """Handle IPCP packet"""
        if not self.is_lcp_opened():
            logger.warning("IPCP packet received but LCP not opened")
            return None
        
        if packet.code == PPPCode.CONFIGURE_REQUEST:
            return await self.handle_ipcp_configure_request(packet)
        elif packet.code == PPPCode.CONFIGURE_ACK:
            await self.handle_ipcp_configure_ack(packet)
        elif packet.code == PPPCode.CONFIGURE_NAK:
            result = await self.handle_ipcp_configure_nak(packet)
            if result is None:  # Need to retry
                retry_request = await self.send_ipcp_configure_request(writer)
                framed = AsyncPPPHandler.frame_data(retry_request)
                writer.write(framed)
                await writer.drain()
        elif packet.code == PPPCode.CONFIGURE_REJECT:
            result = await self.handle_ipcp_configure_reject(packet)
            if result is None:  # Need to retry
                retry_request = await self.send_ipcp_configure_request(writer)
                framed = AsyncPPPHandler.frame_data(retry_request)
                writer.write(framed)
                await writer.drain()
        else:
            logger.debug(f"Unsupported IPCP code: {packet.code}")
        
        return None
    
    async def start_negotiation(self, writer: asyncio.StreamWriter):
        """Start PPP negotiation process"""
        self.negotiation_start_time = time.time()
        
        if not self.is_server:
            # Client initiates negotiation
            logger.info("Starting PPP negotiation as CLIENT - sending initial LCP Configure-Request")
            self.negotiation_initiated = True
            lcp_request = await self.send_lcp_configure_request(writer)
            framed = AsyncPPPHandler.frame_data(lcp_request)
            writer.write(framed)
            await writer.drain()
        else:
            # Server waits for client to initiate
            logger.info("Starting PPP negotiation as SERVER - waiting for client LCP Configure-Request")
            self.lcp_state = PPPState.STARTING
    
    async def handle_keepalive(self, writer: asyncio.StreamWriter):
        """Handle periodic keepalive tasks"""
        # Check if we need to timeout waiting for client
        # In host mode, wait forever for client to connect (no timeout)
        if (self.is_server and not self.negotiation_initiated and 
            self.lcp_state == PPPState.STARTING and
            time.time() - self.negotiation_start_time > self.negotiation_timeout and
            False):  # Disabled timeout in host mode - wait forever for client
            logger.info("Server timeout waiting for client - initiating negotiation")
            self.negotiation_initiated = True
            lcp_request = await self.send_lcp_configure_request(writer)
            framed = AsyncPPPHandler.frame_data(lcp_request)
            writer.write(framed)
            await writer.drain()
        
        if await self.needs_echo():
            echo_request = await self.send_lcp_echo_request(writer)
            framed = AsyncPPPHandler.frame_data(echo_request)
            writer.write(framed)
            await writer.drain()

class AsyncTCPStack:
    """Enhanced async TCP/IP stack with RFC 793 compliance"""
    
    def __init__(self, local_ip="10.0.0.1", remote_ip="10.0.0.2"):
        self.local_ip = socket.inet_aton(local_ip)
        self.remote_ip = socket.inet_aton(remote_ip)
        self.connections: Dict[Tuple[int, int], TCPConnection] = {}
        self.ip_id_counter = 0
        self.proxy = None  # Will be set by AsyncPPPBridge
        
        # Enhanced TCP components
        self.timer_manager = TCPTimerManager()
        self.state_machine = TCPStateMachine(self.timer_manager)
        self.options_handler = TCPOptionsHandler()
        
    def calculate_ip_checksum(self, header: bytes) -> int:
        """Calculate IP header checksum"""
        if len(header) % 2:
            header += b'\x00'
        
        checksum = 0
        for i in range(0, len(header), 2):
            checksum += struct.unpack('!H', header[i:i+2])[0]
        
        while checksum >> 16:
            checksum = (checksum & 0xFFFF) + (checksum >> 16)
        
        return ~checksum & 0xFFFF
    
    def calculate_tcp_checksum(self, src_ip: bytes, dst_ip: bytes, 
                              tcp_segment: bytes) -> int:
        """Calculate TCP checksum including pseudo-header"""
        # Pseudo-header
        pseudo = struct.pack('!4s4sBBH',
                           src_ip, dst_ip,
                           0, 6,  # Reserved, Protocol (TCP)
                           len(tcp_segment))
        
        data = pseudo + tcp_segment
        if len(data) % 2:
            data += b'\x00'
        
        checksum = 0
        for i in range(0, len(data), 2):
            checksum += struct.unpack('!H', data[i:i+2])[0]
        
        while checksum >> 16:
            checksum = (checksum & 0xFFFF) + (checksum >> 16)
        
        return ~checksum & 0xFFFF
    
    def create_ip_packet(self, src_ip: bytes, dst_ip: bytes, 
                        payload: bytes, protocol: int = 6) -> bytes:
        """Create a complete IP packet with checksum"""
        version_ihl = 0x45  # IPv4, 20 byte header
        tos = 0
        total_length = 20 + len(payload)
        self.ip_id_counter = (self.ip_id_counter + 1) & 0xFFFF
        flags_fragment = 0x4000  # Don't fragment
        ttl = 64
        
        # Create header without checksum
        header = struct.pack('!BBHHHBBH4s4s',
                           version_ihl, tos, total_length,
                           self.ip_id_counter, flags_fragment,
                           ttl, protocol, 0,  # checksum = 0 initially
                           src_ip, dst_ip)
        
        # Calculate and insert checksum
        checksum = self.calculate_ip_checksum(header)
        header = header[:10] + struct.pack('!H', checksum) + header[12:]
        
        return header + payload
    
    def create_tcp_segment(self, src_ip: bytes, dst_ip: bytes,
                          src_port: int, dst_port: int,
                          seq: int, ack: int, flags: int,
                          window: int = 8192, data: bytes = b'',
                          options: bytes = b'') -> bytes:
        """Create a TCP segment with proper checksum and options"""
        # Ensure options are padded to 4-byte boundary
        if options:
            padding_needed = (4 - (len(options) % 4)) % 4
            options += b'\x00' * padding_needed
            
        header_len = 20 + len(options)
        data_offset = (header_len // 4) << 4
        
        # Build TCP header
        tcp_header = struct.pack('!HHIIBBHHH',
                               src_port, dst_port,
                               seq, ack,
                               data_offset, flags,
                               window,
                               0,  # checksum (calculated later)
                               0)  # urgent pointer
        
        tcp_segment = tcp_header + options + data
        
        # Calculate checksum
        checksum = self.calculate_tcp_checksum(src_ip, dst_ip, tcp_segment)
        
        # Insert checksum
        tcp_segment = (tcp_segment[:16] + 
                      struct.pack('!H', checksum) + 
                      tcp_segment[18:])
        
        return tcp_segment
    
    def parse_packet(self, packet: bytes) -> Optional[Dict]:
        """Enhanced TCP/IP packet parsing with options support"""
        if len(packet) < 20:
            return None
        
        # Parse IP header
        version_ihl = packet[0]
        ihl = (version_ihl & 0x0F) * 4
        
        if len(packet) < ihl:
            return None
        
        protocol = packet[9]
        if protocol != 6:  # Only handle TCP
            return None
        
        src_ip = packet[12:16]
        dst_ip = packet[16:20]
        
        # Parse TCP header
        tcp_data = packet[ihl:]
        if len(tcp_data) < 20:
            return None
        
        src_port, dst_port = struct.unpack('!HH', tcp_data[0:4])
        seq_num, ack_num = struct.unpack('!II', tcp_data[4:12])
        data_offset_flags = struct.unpack('!BB', tcp_data[12:14])
        tcp_header_len = (data_offset_flags[0] >> 4) * 4
        flags = data_offset_flags[1]
        window = struct.unpack('!H', tcp_data[14:16])[0]
        checksum = struct.unpack('!H', tcp_data[16:18])[0]
        urgent_ptr = struct.unpack('!H', tcp_data[18:20])[0]
        
        # Validate TCP header length
        if tcp_header_len < 20 or tcp_header_len > len(tcp_data):
            return None
        
        # Extract TCP options if present
        options_data = b''
        if tcp_header_len > 20:
            options_data = tcp_data[20:tcp_header_len]
        
        # Extract payload
        payload = tcp_data[tcp_header_len:] if len(tcp_data) > tcp_header_len else b''
        
        return {
            'src_ip': src_ip,
            'dst_ip': dst_ip,
            'src_port': src_port,
            'dst_port': dst_port,
            'seq': seq_num,
            'ack': ack_num,
            'flags': flags,
            'window': window,
            'checksum': checksum,
            'urgent_ptr': urgent_ptr,
            'options': options_data,
            'data': payload
        }
    
    async def process_timers(self):
        """Process expired TCP timers"""
        await self.timer_manager.process_expired_timers()
    
    async def process_tcp_segment(self, segment_info: Dict, writer: asyncio.StreamWriter) -> Optional[bytes]:
        """Process TCP segment using the state machine"""
        key = (segment_info['src_port'], segment_info['dst_port'])
        conn = self.connections.get(key)
        
        # Debug connection state and packet info
        flags = segment_info.get('flags', 0)
        seq = segment_info.get('seq', 0)
        data = segment_info.get('data', b'')
        flag_names = []
        if flags & 0x01: flag_names.append("FIN")
        if flags & 0x02: flag_names.append("SYN") 
        if flags & 0x04: flag_names.append("RST")
        if flags & 0x08: flag_names.append("PSH")
        if flags & 0x10: flag_names.append("ACK")
        
        if conn:
            logger.debug(f"TCP: Processing {'/'.join(flag_names) if flag_names else 'NONE'} packet - State: {conn.state.name}, seq={seq}, data_len={len(data)}")
        else:
            logger.debug(f"TCP: Processing {'/'.join(flag_names) if flag_names else 'NONE'} packet - NO CONNECTION, seq={seq}, data_len={len(data)}")
        
        if not conn:
            # Create new connection for SYN segments
            if segment_info['flags'] & TCPFlags.SYN:
                conn = TCPConnection(
                    state=TCPState.LISTEN,
                    src_ip=segment_info['src_ip'],
                    dst_ip=segment_info['dst_ip'],
                    src_port=segment_info['src_port'],
                    dst_port=segment_info['dst_port'],
                    initial_seq=random.randint(1, 0x7FFFFFFF),
                    window_size=8192
                )
                # Initialize sequence numbers
                conn.seq_num = conn.initial_seq
                conn.snd_nxt = conn.initial_seq
                conn.snd_una = conn.initial_seq
                
                self.connections[key] = conn
            else:
                # No connection exists for non-SYN segment
                return await self.state_machine.process_segment(
                    TCPConnection(state=TCPState.CLOSED), 
                    segment_info, self, writer
                )
        
        # Process segment through state machine
        return await self.state_machine.process_segment(conn, segment_info, self, writer)

class AsyncServiceProxy:
    """Async proxy for local services with SOCKS support"""
    
    def __init__(self, tcp_stack: AsyncTCPStack, 
                 socks_host: Optional[str] = None,
                 socks_port: int = 1080,
                 config: Optional[Any] = None):
        self.tcp_stack = tcp_stack
        self.socks_host = socks_host
        self.socks_port = socks_port
        self.service_tasks = {}
        self.pending_connections = {}  # Track pending service connections
        self.active_connections = {}  # Track bidirectional proxy connections
        
        # Service port mapping from config
        self.services = {}
        if config and hasattr(config, 'services'):
            for port, service_config in config.services.items():
                if service_config.enabled:
                    self.services[int(port)] = (service_config.host, service_config.port)
                    logger.info(f"Service mapping: {port} -> {service_config.host}:{service_config.port} ({service_config.name})")
        else:
            # Fallback to hardcoded mappings
            self.services = {
                22: ('127.0.0.1', 22),    # SSH
                80: ('127.0.0.1', 80),    # HTTP
                443: ('127.0.0.1', 443),  # HTTPS
                8080: ('127.0.0.1', 8080),
                3000: ('127.0.0.1', 3000),
                5000: ('127.0.0.1', 5000),
                8000: ('127.0.0.1', 8000),
            }
            logger.info("Using fallback service mappings")
    
    async def connect_through_socks(self, target_host: str, 
                                   target_port: int) -> Tuple[Optional[asyncio.StreamReader], 
                                                              Optional[asyncio.StreamWriter]]:
        """Connect through SOCKS5 proxy"""
        try:
            # Connect to SOCKS proxy
            reader, writer = await asyncio.open_connection(
                self.socks_host, self.socks_port
            )
            
            # SOCKS5 handshake
            writer.write(b'\x05\x01\x00')  # Ver 5, 1 method, no auth
            await writer.drain()
            
            response = await reader.read(2)
            if response[0] != 0x05 or response[1] != 0x00:
                raise Exception("SOCKS handshake failed")
            
            # Connection request
            if target_host == '127.0.0.1':
                # IPv4 address
                addr_type = b'\x01'
                addr_data = socket.inet_aton(target_host)
            else:
                # Domain name
                addr_type = b'\x03'
                addr_data = bytes([len(target_host)]) + target_host.encode()
            
            request = b'\x05\x01\x00' + addr_type + addr_data
            request += struct.pack('!H', target_port)
            
            writer.write(request)
            await writer.drain()
            
            response = await reader.read(10)
            if response[1] != 0x00:
                raise Exception(f"SOCKS connection failed: {response[1]}")
            
            return reader, writer
            
        except Exception as e:
            logger.error(f"SOCKS connection failed: {e}")
            return None, None
    
    async def connect_to_service(self, host: str, port: int) -> Tuple[Optional[asyncio.StreamReader], 
                                                                       Optional[asyncio.StreamWriter]]:
        """Connect to service directly or through SOCKS"""
        try:
            if self.socks_host:
                return await self.connect_through_socks(host, port)
            else:
                return await asyncio.open_connection(host, port)
        except Exception as e:
            logger.error(f"Service connection failed: {e}")
            return None, None
    
    async def handle_connection(self, conn: TCPConnection, 
                               writer: asyncio.StreamWriter) -> bytes:
        """Handle established TCP connection"""
        key = (conn.src_port, conn.dst_port)
        logger.info(f"ServiceProxy: Handling connection {key[0]}->{key[1]}")
        
        # Create task to forward data from service (or restart if previous one finished)
        if key not in self.service_tasks or self.service_tasks[key].done():
            if key in self.service_tasks and self.service_tasks[key].done():
                logger.info(f"ServiceProxy: Previous forward task completed, starting new one for {key[0]}->{key[1]}")
            else:
                logger.info(f"ServiceProxy: Starting forward task for {key[0]}->{key[1]}")
            task = asyncio.create_task(
                self.forward_service_data(conn, writer)
            )
            self.service_tasks[key] = task
        else:
            logger.debug(f"ServiceProxy: Forward task already exists for {key[0]}->{key[1]}")
        
        # Process any pending data in connection
        if conn.send_buffer:
            data = conn.send_buffer
            conn.send_buffer = b''
            logger.info(f"ServiceProxy: Sending {len(data)} bytes of buffered data to service")
            
            # Reconnect to service if connection was closed
            if not conn.local_sock:
                logger.info(f"ServiceProxy: Reconnecting to service for {key[0]}->{key[1]}")
                service_info = self.services.get(conn.dst_port)
                if service_info:
                    host, port = service_info
                    try:
                        conn.local_reader, conn.local_sock = await self.connect_to_service(host, port)
                        logger.info(f"ServiceProxy: Reconnected to {host}:{port}")
                    except Exception as e:
                        logger.error(f"ServiceProxy: Failed to reconnect to service: {e}")
                        return b''
            
            if conn.local_sock:
                conn.local_sock.write(data)
                await conn.local_sock.drain()
        
        return b''  # Response handled by forward_service_data task
    
    async def forward_service_data(self, conn: TCPConnection,
                                  serial_writer: asyncio.StreamWriter):
        """Forward data from service to PPP client"""
        logger.info(f"ServiceProxy: Starting data forwarding for {conn.src_port}->{conn.dst_port}")
        try:
            while conn.state == TCPState.ESTABLISHED:
                if conn.local_reader:
                    data = await asyncio.wait_for(
                        conn.local_reader.read(4096), 
                        timeout=0.1
                    )
                    
                    if data:
                        logger.info(f"ServiceProxy: Received {len(data)} bytes from service, forwarding to PPP")
                        # Create TCP packet with data - use rcv_nxt for ACK number
                        tcp_seg = self.tcp_stack.create_tcp_segment(
                            conn.dst_ip, conn.src_ip,
                            conn.dst_port, conn.src_port,
                            conn.seq_num, conn.rcv_nxt,  # Use rcv_nxt instead of ack_num
                            TCPFlags.PSH | TCPFlags.ACK,
                            data=data
                        )
                        
                        ip_packet = self.tcp_stack.create_ip_packet(
                            conn.dst_ip, conn.src_ip, tcp_seg
                        )
                        
                        # Send through PPP
                        ppp_frame = struct.pack('!BBH', 0xFF, 0x03, 0x0021) + ip_packet
                        framed = AsyncPPPHandler.frame_data(ppp_frame)
                        
                        serial_writer.write(framed)
                        await serial_writer.drain()
                        
                        conn.seq_num += len(data)
                    else:
                        # Connection closed by service
                        break
                        
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.error(f"Forward error: {e}")
        finally:
            # Clean up connection
            if conn.local_sock:
                conn.local_sock.close()
                await conn.local_sock.wait_closed()
            
            key = (conn.src_port, conn.dst_port)
            if key in self.service_tasks:
                del self.service_tasks[key]
            # Do NOT delete the TCP connection - it should persist for multiple service connections
            # The TCP connection will be cleaned up when the PPP client closes it
            logger.debug(f"ServiceProxy: Service connection closed for {key[0]}->{key[1]}, but keeping TCP connection alive")
    
    async def establish_bidirectional_forwarding(self, conn: TCPConnection, 
                                               host: str, port: int, 
                                               serial_writer: asyncio.StreamWriter) -> bool:
        """
        Establish bidirectional forwarding between PPP and service using production pattern.
        
        This is called ONCE when TCP connection reaches ESTABLISHED state.
        Returns True if forwarding was successfully established.
        """
        try:
            # Establish connection to target service
            logger.info(f"[CONNECT] Establishing bidirectional forwarding to {host}:{port}")
            logger.info(f"[CONNECT] Connection: {conn.src_port}->{conn.dst_port}")
            
            try:
                conn.local_reader, conn.local_writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=10.0
                )
            except ConnectionRefusedError:
                logger.error(f"[ERROR] Connection refused to {host}:{port} - is the service running?")
                logger.error(f"[ERROR] For echo server test, run: python3 simple_tcp_test.py")
                raise
            except Exception as e:
                logger.error(f"[ERROR] Failed to connect to {host}:{port}: {e}")
                raise
            logger.info(f"[SUCCESS] Connected to target service {host}:{port}")
            
            # Initialize shutdown event and data queue
            conn._shutdown_event = asyncio.Event()
            conn._ppp_data_queue = asyncio.Queue()
            
            # Start bidirectional forwarding using asyncio.gather() pattern
            key = f"{conn.src_port}->{conn.dst_port}"
            conn.proxy_task = asyncio.create_task(
                self._run_bidirectional_forwarding(conn, serial_writer)
            )
            self.active_connections[key] = conn
            
            logger.info(f"[READY] Bidirectional forwarding established for {conn.src_port}->{conn.dst_port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to establish forwarding to {host}:{port}: {e}")
            await self._cleanup_connection(conn)
            return False
    
    async def _run_bidirectional_forwarding(self, conn: TCPConnection, 
                                          serial_writer: asyncio.StreamWriter):
        """
        Core bidirectional forwarding logic using asyncio.gather() pattern.
        
        This is the proven pattern used in production proxies.
        Both directions run concurrently and coordinate shutdown.
        """
        logger.info(f"Starting bidirectional forwarding: PPP({conn.src_port}) <-> Service({conn.dst_port})")
        
        try:
            # Run both directions concurrently using asyncio.gather()
            # If either direction fails or completes, both stop
            await asyncio.gather(
                self._forward_ppp_to_service(conn),  # PPP -> Service
                self._forward_service_to_ppp(conn, serial_writer),  # Service -> PPP
                return_exceptions=False  # Stop both on first exception
            )
            
        except Exception as e:
            logger.error(f"[DEBUG] Bidirectional forwarding error for {conn.src_port}->{conn.dst_port}: {e}")
        finally:
            logger.info(f"[DEBUG] GATHER: Bidirectional forwarding ended for {conn.src_port}->{conn.dst_port}")
            await self._cleanup_connection(conn)
    
    async def _forward_ppp_to_service(self, conn: TCPConnection):
        """
        Forward data from PPP client to local service.
        
        This replaces the data handling in _handle_established_state.
        Data is queued here instead of being processed inline.
        """
        logger.debug("Starting PPP -> Service forwarding")
        
        try:
            while conn.state == TCPState.ESTABLISHED and not conn._shutdown_event.is_set():
                try:
                    # Wait for data from PPP side (populated by TCP state machine)
                    data = await asyncio.wait_for(
                        conn._ppp_data_queue.get(),
                        timeout=1.0
                    )
                    
                    if not data:  # Shutdown signal
                        break
                    
                    # Forward to service
                    conn.local_writer.write(data)
                    await conn.local_writer.drain()
                    
                    logger.debug(f"Forwarded {len(data)} bytes PPP -> Service")
                    
                except asyncio.TimeoutError:
                    continue  # Check shutdown condition
                    
        except Exception as e:
            logger.error(f"PPP -> Service forwarding error: {e}")
            raise
        finally:
            logger.debug("PPP -> Service forwarding stopped")
    
    async def _forward_service_to_ppp(self, conn: TCPConnection, 
                                    serial_writer: asyncio.StreamWriter):
        """
        Forward data from local service to PPP client.
        
        This is event-driven (no timeouts) and coordinates with PPP side.
        """
        logger.debug("Starting Service -> PPP forwarding")
        
        try:
            logger.info(f"[DEBUG] Service->PPP forwarding started for {conn.src_port}->{conn.dst_port}")
            while conn.state == TCPState.ESTABLISHED and not conn._shutdown_event.is_set():
                logger.debug(f"[DEBUG] Service->PPP: Waiting for data from service, state={conn.state.name}")
                try:
                    # Read data from service with timeout to avoid blocking forever
                    data = await asyncio.wait_for(conn.local_reader.read(4096), timeout=1.0)
                    
                    if not data:  # Service closed connection
                        # Double-check if connection is actually closed by checking if we can write
                        if conn.local_writer.is_closing():
                            logger.info(f"[DEBUG] Service->PPP: Service connection actually closed, initiating shutdown")
                            break
                        else:
                            logger.debug(f"[DEBUG] Service->PPP: Got 0 bytes but connection still open, continuing...")
                            continue
                    
                    logger.info(f"[DEBUG] Service->PPP: Received {len(data)} bytes from service: {data[:50]}")
                except asyncio.TimeoutError:
                    # No data available, continue checking for shutdown
                    logger.debug(f"[DEBUG] Service->PPP: Timeout waiting for service data, continuing...")
                    continue
                
                # Send data through PPP
                logger.info(f"[DEBUG] Service->PPP: Sending {len(data)} bytes to PPP client")
                await self._send_data_to_ppp(conn, data, serial_writer)
                logger.info(f"[DEBUG] Service->PPP: Successfully forwarded {len(data)} bytes Service -> PPP")
                
        except Exception as e:
            logger.error(f"Service -> PPP forwarding error: {e}")
            raise
        finally:
            logger.info(f"[DEBUG] Service->PPP forwarding stopped for {conn.src_port}->{conn.dst_port}")
            conn._shutdown_event.set()  # Signal other direction to stop
    
    async def _send_data_to_ppp(self, conn: TCPConnection, data: bytes, 
                              serial_writer: asyncio.StreamWriter):
        """Send data from service back to PPP client"""
        # Create TCP segment with PSH+ACK flags
        tcp_segment = self.tcp_stack.create_tcp_segment(
            conn.dst_ip, conn.src_ip,  # Swap src/dst for response
            conn.dst_port, conn.src_port,
            conn.seq_num, conn.rcv_nxt,  # Use rcv_nxt for proper ACK
            TCPFlags.PSH | TCPFlags.ACK,
            data=data
        )
        
        # Create IP packet
        ip_packet = self.tcp_stack.create_ip_packet(
            conn.dst_ip, conn.src_ip, tcp_segment
        )
        
        # Frame as PPP and send
        ppp_frame = struct.pack('!BBH', 0xFF, 0x03, 0x0021) + ip_packet
        framed = AsyncPPPHandler.frame_data(ppp_frame)
        
        serial_writer.write(framed)
        await serial_writer.drain()
        
        # Update sequence number
        conn.seq_num += len(data)
    
    async def handle_ppp_data(self, conn: TCPConnection, data: bytes):
        """
        Called by TCP state machine when data arrives from PPP.
        
        Instead of forwarding directly, queue it for the forwarding task.
        This decouples TCP processing from data forwarding.
        """
        if (hasattr(conn, '_ppp_data_queue') and hasattr(conn, 'proxy_task') and 
            conn.proxy_task and not conn.proxy_task.done()):
            try:
                await conn._ppp_data_queue.put(data)
                logger.info(f"[QUEUE] Queued {len(data)} bytes for PPP->Service forwarding: {data[:20]}")
            except Exception as e:
                logger.error(f"[ERROR] Failed to queue PPP data: {e}")
        else:
            logger.info(f"[RECONNECT] No forwarding task available, need to reconnect for {len(data)} bytes")
            # Store data in connection buffer and trigger reconnection
            conn.send_buffer = data
            
            # Trigger service proxy reconnection by calling handle_connection
            # This will restart the forwarding task and reconnect to the service
            key = (conn.src_port, conn.dst_port)
            logger.info(f"[RECONNECT] Triggering service reconnection for {key[0]}->{key[1]}")
            await self.handle_connection(conn, None)  # writer not needed for reconnection
    
    async def _cleanup_connection(self, conn: TCPConnection):
        """Clean up connection resources with proper coordination"""
        logger.info(f"[DEBUG] CLEANUP: Cleaning up bidirectional connection {conn.src_port}->{conn.dst_port}")
        
        # Signal shutdown to forwarding tasks
        if hasattr(conn, '_shutdown_event') and conn._shutdown_event:
            conn._shutdown_event.set()
        
        # Cancel proxy task
        if hasattr(conn, 'proxy_task') and conn.proxy_task and not conn.proxy_task.done():
            conn.proxy_task.cancel()
            try:
                await conn.proxy_task
            except asyncio.CancelledError:
                pass
        
        # Close service connection
        if conn.local_writer:
            conn.local_writer.close()
            try:
                await conn.local_writer.wait_closed()
            except Exception:
                pass
        
        # Clear references
        conn.local_reader = None
        conn.local_writer = None
        if hasattr(conn, 'proxy_task'):
            conn.proxy_task = None
        
        # Remove from active connections
        key = f"{conn.src_port}->{conn.dst_port}"
        self.active_connections.pop(key, None)

class AsyncPPPBridge:
    """Main async PPP to services bridge"""
    
    def __init__(self, serial_port: str, baudrate: int = 115200,
                 socks_host: Optional[str] = None, socks_port: int = 1080,
                 config: Optional[Any] = None):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.config = config  # Store config for later use
        
        # Get IP configuration from config or use defaults
        if config and hasattr(config, 'network'):
            self.local_ip = getattr(config.network, 'local_ip', '10.0.0.1')
            self.remote_ip = getattr(config.network, 'remote_ip', '10.0.0.2')
        else:
            self.local_ip = '10.0.0.1'
            self.remote_ip = '10.0.0.2'
            
        # Determine if we're server or client based on IP
        # Convention: 10.0.0.1 is server (host), 10.0.0.2 is client
        is_server = (self.local_ip == "10.0.0.1")
        
        self.ppp_handler = AsyncPPPHandler()
        self.ppp_negotiator = AsyncPPPNegotiator(self.local_ip, self.remote_ip, is_server)
        self.tcp_stack = AsyncTCPStack(self.local_ip, self.remote_ip)
        self.proxy = AsyncServiceProxy(self.tcp_stack, socks_host, socks_port, config)
        self.tcp_stack.proxy = self.proxy  # Set proxy reference for bidirectional forwarding
        self.negotiation_started = False
        self.tcp_forwarder = None  # Will be initialized for client mode
        
    async def handle_tcp_packet(self, packet_info: Dict, 
                               writer: asyncio.StreamWriter) -> Optional[bytes]:
        """Process TCP packet using enhanced state machine"""
        
        # If we're a client and have a forwarder, check if this packet is for it
        if not self.ppp_negotiator.is_server and self.tcp_forwarder:
            # Check if this packet is for a forwarded connection
            dst_port = packet_info.get('dst_port')
            if dst_port in self.tcp_forwarder.connections:
                # Let the forwarder handle packets for its connections
                await self.tcp_forwarder.handle_incoming_packet(packet_info)
                return None  # Packet handled by forwarder
        
        # Check if this is for a known service (server mode)
        if self.ppp_negotiator.is_server:
            src_port = packet_info.get('src_port', 0)
            dst_port = packet_info.get('dst_port', 0)
            flags = packet_info.get('flags', 0)
            
            logger.debug(f"Server received TCP packet: {src_port}->{dst_port}, flags=0x{flags:02x}")
            
            if (flags & TCPFlags.SYN and 
                not (flags & TCPFlags.ACK) and
                dst_port in self.proxy.services):
                
                logger.info(f"Server received SYN for service port {dst_port}")
                
                # For SYN to known service, set up service connection
                key = (src_port, dst_port)
                service_host, service_port = self.proxy.services[dst_port]
                reader, writer_svc = await self.proxy.connect_to_service(
                    service_host, service_port
                )
                
                if reader and writer_svc:
                    # Store service connection info for later use
                    self.proxy.pending_connections[key] = (reader, writer_svc)
                    logger.info(f"Service connection prepared: {service_host}:{service_port}")
                else:
                    logger.error(f"Failed to connect to service {service_host}:{service_port}")
            elif dst_port not in self.proxy.services:
                logger.debug(f"No service configured for port {dst_port}")
        
        # Process through enhanced TCP stack
        response = await self.tcp_stack.process_tcp_segment(packet_info, writer)
        
        if response:
            logger.debug(f"TCP stack generated {len(response)} byte response")
        else:
            logger.debug("TCP stack generated no response")
        
        # Handle connection establishment for service proxy
        key = (packet_info['src_port'], packet_info['dst_port'])
        conn = self.tcp_stack.connections.get(key)
        
        # Check if connection is now established and needs service setup
        if (conn and conn.state == TCPState.ESTABLISHED and 
            key in self.proxy.pending_connections):
            
            logger.info(f"Setting up service forwarding: {packet_info['src_port']} -> {packet_info['dst_port']}")
            
            # Connection established, set up service forwarding
            reader, writer_svc = self.proxy.pending_connections.pop(key)
            conn.local_reader = reader
            conn.local_sock = writer_svc
            
            # Start forwarding task
            asyncio.create_task(self.proxy.handle_connection(conn, writer))
            
            logger.info(f"Service connection established: {packet_info['src_port']} -> {packet_info['dst_port']}")
        
        return response
    
    async def serial_reader(self, reader: asyncio.StreamReader,
                          writer: asyncio.StreamWriter):
        """Read from serial port and process PPP frames"""
        try:
            # Store writer for port forwarding
            self.serial_writer = writer
            
            # Start PPP negotiation
            if not self.negotiation_started:
                await self.ppp_negotiator.start_negotiation(writer)
                self.negotiation_started = True
            
            # Create keepalive and timer processing tasks
            keepalive_task = asyncio.create_task(self.keepalive_handler(writer))
            timer_task = asyncio.create_task(self.tcp_timer_handler())
            
            # Wait for PPP to be ready before starting client forwarders
            if not self.ppp_negotiator.is_server:
                logger.info("[CLIENT] Detected client mode - starting forwarder task")
                asyncio.create_task(self._start_client_forwarders())
            else:
                logger.info("[HOST] Detected host mode - no client forwarders needed")
            
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                
                frames = await self.ppp_handler.process_data(data)
                
                for frame in frames:
                    if len(frame) < 4:
                        continue
                    
                    protocol = struct.unpack('!H', frame[2:4])[0]
                    
                    if protocol == PPPProtocol.IP:  # IP traffic
                        # Only process IP if both LCP and IPCP are opened
                        if self.ppp_negotiator.is_ready_for_ip():
                            ip_packet = frame[4:]
                            packet_info = self.tcp_stack.parse_packet(ip_packet)
                            
                            if packet_info:
                                response = await self.handle_tcp_packet(
                                    packet_info, writer
                                )
                                
                                if response:
                                    ppp_frame = struct.pack('!BBH', 0xFF, 0x03, PPPProtocol.IP) + response
                                    framed = AsyncPPPHandler.frame_data(ppp_frame)
                                    writer.write(framed)
                                    await writer.drain()
                        else:
                            logger.debug("IP packet received but PPP negotiation not complete")
                    
                    elif protocol in [PPPProtocol.LCP, PPPProtocol.IPCP]:
                        # Handle PPP control protocols
                        response = await self.ppp_negotiator.handle_ppp_packet(frame, writer)
                        if response:
                            framed = AsyncPPPHandler.frame_data(response)
                            writer.write(framed)
                            await writer.drain()
                    
                    else:
                        logger.debug(f"Unsupported protocol: 0x{protocol:04X}")
                        
        except Exception as e:
            logger.error(f"Serial reader error: {e}")
        finally:
            keepalive_task.cancel()
            timer_task.cancel()
            writer.close()
            await writer.wait_closed()
    
    async def keepalive_handler(self, writer: asyncio.StreamWriter):
        """Handle periodic keepalive and maintenance tasks"""
        try:
            while True:
                await asyncio.sleep(1.0)  # Check every second
                await self.ppp_negotiator.handle_keepalive(writer)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Keepalive handler error: {e}")
    
    async def tcp_timer_handler(self):
        """Handle TCP timer processing"""
        try:
            while True:
                await asyncio.sleep(0.1)  # Check every 100ms for more responsive timers
                await self.tcp_stack.process_timers()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"TCP timer handler error: {e}")
    
    async def _start_client_forwarders(self):
        """Start TCP forwarders for client mode"""
        logger.info("[CLIENT] Waiting for PPP negotiation to complete...")
        
        # Wait for PPP negotiation to complete
        wait_count = 0
        while not self.ppp_negotiator.is_ready_for_ip():
            wait_count += 1
            if wait_count % 5 == 0:
                logger.info(f"[CLIENT] Still waiting for PPP... (LCP: {self.ppp_negotiator.lcp_state}, IPCP: {self.ppp_negotiator.ipcp_state})")
            await asyncio.sleep(1)
        
        logger.info("[CLIENT] PPP ready - starting client TCP forwarders")
        
        try:
            from tcp_forwarder import TCPPortForwarder
            logger.info("[CLIENT] Creating TCPPortForwarder instance")
            self.tcp_forwarder = TCPPortForwarder(self)
            
            # Get config or use defaults
            logger.info(f"[CLIENT] Config available: {self.config is not None}")
            if self.config and hasattr(self.config, 'port_forwards'):
                logger.info(f"[CLIENT] Port forwards configured: {self.config.port_forwards}")
            else:
                logger.info(f"[CLIENT] No port_forwards attribute found")
            
            await self.tcp_forwarder.start_forwarders(self.config)
            
            logger.info("")
            logger.info("Client port forwards active:")
            logger.info("  SSH:   ssh localhost -p 2222")
            logger.info("  HTTP:  http://localhost:8080")
            logger.info("  HTTPS: https://localhost:8443")
            
        except Exception as e:
            logger.error(f"Failed to start client forwarders: {e}")
    
    async def run(self):
        """Main async run loop"""
        logger.info(f"Starting async PPP bridge on {self.serial_port}")
        role = "SERVER (Host)" if self.ppp_negotiator.is_server else "CLIENT"
        logger.info(f"Running as: {role}")
        logger.info(f"Local IP: {self.local_ip}, Remote IP: {self.remote_ip}")
        logger.info(f"Magic Number: 0x{self.ppp_negotiator.magic_number:08X}")
        logger.info(f"MRU: {self.ppp_negotiator.mru} bytes")
        
        if self.proxy.socks_host:
            logger.info(f"Using SOCKS5 proxy: {self.proxy.socks_host}:{self.proxy.socks_port}")
        else:
            logger.info("Direct connection mode")
        
        logger.info(f"Available services: {list(self.proxy.services.keys())}")
        logger.info("Service mappings:")
        for port, (host, target_port) in self.proxy.services.items():
            logger.info(f"  {port} -> {host}:{target_port}")
        logger.info("PPP negotiation will begin automatically when client connects")
        logger.info("")
        logger.info("Usage instructions:")
        if self.ppp_negotiator.is_server:
            logger.info("  This is the SERVER (host). It provides local services to PPP clients.")
            logger.info(f"  Clients should connect to {self.remote_ip}:<port> to access services")
        else:
            logger.info("  This is the CLIENT. It can connect to services on the PPP server.")
            logger.info(f"  Connect to {self.remote_ip}:<port> to access server services")
        
        # Open serial connection
        reader, writer = await serial_asyncio.open_serial_connection(
            url=self.serial_port,
            baudrate=self.baudrate
        )
        
        await self.serial_reader(reader, writer)

async def main():
    """Async main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Async Python SLiRP implementation')
    parser.add_argument('serial_port', help='Serial port (e.g., /dev/ttyUSB0)')
    parser.add_argument('-b', '--baudrate', type=int, default=115200)
    parser.add_argument('--socks-host', help='SOCKS5 proxy host')
    parser.add_argument('--socks-port', type=int, default=1080)
    parser.add_argument('-d', '--debug', action='store_true')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    bridge = AsyncPPPBridge(
        args.serial_port,
        args.baudrate,
        args.socks_host,
        args.socks_port
    )
    
    await bridge.run()

if __name__ == '__main__':
    asyncio.run(main())