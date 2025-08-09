#!/usr/bin/env python3
"""
TCP Flow Debugging Tool for PyLiRP SSH Issues

This tool analyzes the actual TCP segments and data flow to identify
where the SSH connection is breaking down.
"""

import struct
import socket
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class TCPFlowDebugger:
    """Debug TCP flow at packet level"""
    
    def __init__(self):
        self.packets_seen = 0
        self.data_packets = 0
        self.ssh_handshake_packets = []
        self.ssh_data_packets = []
        
    def analyze_tcp_segment(self, packet_info: Dict[str, Any], data: bytes = b''):
        """Analyze individual TCP segment in detail"""
        self.packets_seen += 1
        
        src_port = packet_info.get('src_port', 0)
        dst_port = packet_info.get('dst_port', 0) 
        flags = packet_info.get('flags', 0)
        seq = packet_info.get('seq', 0)
        ack = packet_info.get('ack', 0)
        
        # Decode flags
        flag_names = []
        if flags & 0x01: flag_names.append("FIN")
        if flags & 0x02: flag_names.append("SYN") 
        if flags & 0x04: flag_names.append("RST")
        if flags & 0x08: flag_names.append("PSH")
        if flags & 0x10: flag_names.append("ACK")
        if flags & 0x20: flag_names.append("URG")
        
        logger.info(f"TCP SEGMENT #{self.packets_seen}: {src_port}->{dst_port} "
                   f"flags=[{','.join(flag_names)}] seq={seq} ack={ack} "
                   f"data_len={len(data)}")
        
        # Analyze SSH-specific traffic
        if dst_port == 22 or src_port == 22:
            self._analyze_ssh_packet(src_port, dst_port, flags, seq, ack, data)
        
        # Log data content for debugging
        if data:
            self.data_packets += 1
            logger.info(f"  DATA: {len(data)} bytes")
            self._analyze_data_content(data)
            
    def _analyze_ssh_packet(self, src_port: int, dst_port: int, flags: int, 
                           seq: int, ack: int, data: bytes):
        """Analyze SSH-specific packets"""
        direction = "CLIENT->SSH" if dst_port == 22 else "SSH->CLIENT"
        
        if data:
            self.ssh_data_packets.append({
                'direction': direction,
                'seq': seq,
                'ack': ack,
                'data_len': len(data),
                'data': data[:100]  # First 100 bytes for analysis
            })
            
            logger.info(f"  SSH {direction}: {len(data)} bytes of data")
            
            # Try to identify SSH protocol stages
            if len(data) > 4:
                if data.startswith(b'SSH-'):
                    logger.info(f"    SSH Version Exchange: {data[:50]}")
                elif self._is_ssh_binary_packet(data):
                    logger.info(f"    SSH Binary Packet: packet_len={self._get_ssh_packet_length(data)}")
                else:
                    logger.info(f"    SSH Data: {data[:20].hex()} ...")
        else:
            logger.info(f"  SSH {direction}: Control packet (no data)")
            
    def _analyze_data_content(self, data: bytes):
        """Analyze the content of data packets"""
        if not data:
            return
            
        # Check if it's printable ASCII (like SSH version string)
        try:
            ascii_data = data.decode('ascii', errors='ignore')
            if ascii_data.isprintable() and len(ascii_data) > 4:
                logger.info(f"    ASCII Content: {ascii_data[:50]}")
                return
        except:
            pass
            
        # Check for SSH protocol markers
        if data.startswith(b'SSH-'):
            logger.info(f"    SSH Version String: {data[:50]}")
        elif self._is_ssh_binary_packet(data):
            packet_len = self._get_ssh_packet_length(data)
            logger.info(f"    SSH Binary Packet: length={packet_len}")
        else:
            # Show hex dump for binary data
            hex_str = data[:16].hex()
            logger.info(f"    Hex Data: {hex_str} ...")
            
    def _is_ssh_binary_packet(self, data: bytes) -> bool:
        """Check if data looks like SSH binary packet"""
        if len(data) < 5:
            return False
        try:
            # SSH packets start with 4-byte length field
            packet_len = struct.unpack('!I', data[:4])[0]
            # Reasonable SSH packet length (not too small, not too big)
            return 1 <= packet_len <= 35000 and packet_len <= len(data) + 4
        except:
            return False
            
    def _get_ssh_packet_length(self, data: bytes) -> int:
        """Get SSH packet length from header"""
        try:
            return struct.unpack('!I', data[:4])[0]
        except:
            return 0
            
    def generate_report(self) -> str:
        """Generate debugging report"""
        report = [
            f"TCP Flow Analysis Report",
            f"=" * 40,
            f"Total TCP segments processed: {self.packets_seen}",
            f"Segments with data: {self.data_packets}",
            f"SSH data packets: {len(self.ssh_data_packets)}",
            "",
        ]
        
        if self.ssh_data_packets:
            report.append("SSH Data Packet Summary:")
            for i, pkt in enumerate(self.ssh_data_packets[:10]):  # Show first 10
                report.append(f"  {i+1}. {pkt['direction']}: {pkt['data_len']} bytes (seq={pkt['seq']})")
                
        return "\n".join(report)

# Global debugger instance
tcp_debugger = TCPFlowDebugger()

def debug_tcp_packet(packet_info: Dict[str, Any], data: bytes = b''):
    """Debug a TCP packet - call this from pySLiRP.py"""
    tcp_debugger.analyze_tcp_segment(packet_info, data)

def debug_report():
    """Generate and log debugging report"""
    report = tcp_debugger.generate_report()
    logger.info(f"\n{report}")
    return report