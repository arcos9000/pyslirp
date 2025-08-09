#!/usr/bin/env python3
"""
Test script to verify PPP negotiation between client and host
"""

import asyncio
import logging
import sys
import os
import time

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pySLiRP import AsyncPPPNegotiator, AsyncPPPHandler

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_negotiation():
    """Test PPP negotiation logic"""
    
    # Create server negotiator (host with IP 10.0.0.1)
    server = AsyncPPPNegotiator(local_ip="10.0.0.1", remote_ip="10.0.0.2", is_server=True)
    
    # Create client negotiator (client with IP 10.0.0.2)
    client = AsyncPPPNegotiator(local_ip="10.0.0.2", remote_ip="10.0.0.1", is_server=False)
    
    logger.info("=" * 60)
    logger.info("Testing PPP Negotiation Logic")
    logger.info("=" * 60)
    
    # Test 1: Verify roles
    logger.info("\nTest 1: Role Assignment")
    logger.info(f"Server (10.0.0.1) is_server: {server.is_server} (should be True)")
    logger.info(f"Client (10.0.0.2) is_server: {client.is_server} (should be False)")
    assert server.is_server == True, "Server should have is_server=True"
    assert client.is_server == False, "Client should have is_server=False"
    logger.info("✓ Role assignment correct")
    
    # Test 2: Verify initial states
    logger.info("\nTest 2: Initial States")
    logger.info(f"Server LCP state: {server.lcp_state.name}")
    logger.info(f"Client LCP state: {client.lcp_state.name}")
    assert server.lcp_state.name == "INITIAL", "Server should start in INITIAL state"
    assert client.lcp_state.name == "INITIAL", "Client should start in INITIAL state"
    logger.info("✓ Initial states correct")
    
    # Test 3: Test negotiation initiation
    logger.info("\nTest 3: Negotiation Initiation")
    
    # Mock writer for testing
    class MockWriter:
        def __init__(self):
            self.data = []
        def write(self, data):
            self.data.append(data)
        async def drain(self):
            pass
    
    server_writer = MockWriter()
    client_writer = MockWriter()
    
    # Start negotiation
    await server.start_negotiation(server_writer)
    await client.start_negotiation(client_writer)
    
    logger.info(f"Server sent {len(server_writer.data)} packets")
    logger.info(f"Client sent {len(client_writer.data)} packets")
    
    # Server should wait, client should send
    assert len(server_writer.data) == 0, "Server should not send initial packet"
    assert len(client_writer.data) == 1, "Client should send initial LCP Configure-Request"
    logger.info("✓ Client initiates, server waits")
    
    # Test 4: Verify server timeout mechanism
    logger.info("\nTest 4: Server Timeout Mechanism")
    server2 = AsyncPPPNegotiator(local_ip="10.0.0.1", remote_ip="10.0.0.2", is_server=True)
    server2_writer = MockWriter()
    
    await server2.start_negotiation(server2_writer)
    server2.negotiation_timeout = 0.1  # Set short timeout for testing
    
    # Wait for timeout
    await asyncio.sleep(0.2)
    await server2.handle_keepalive(server2_writer)
    
    assert len(server2_writer.data) == 1, "Server should send packet after timeout"
    logger.info("✓ Server timeout mechanism works")
    
    logger.info("\n" + "=" * 60)
    logger.info("All tests passed!")
    logger.info("PPP negotiation logic is correctly configured for client/host communication")
    logger.info("=" * 60)

if __name__ == '__main__':
    asyncio.run(test_negotiation())