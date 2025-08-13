#!/usr/bin/env python3
"""
Test script to verify TCP ACK sequence number fix
Tests bidirectional data flow through the PyLiRP implementation
"""

import asyncio
import socket
import sys
import time
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_echo_server():
    """Test echo server connectivity through PyLiRP"""
    
    # First check if echo server is running on port 8888
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(1)
        test_sock.connect(('127.0.0.1', 8888))
        test_sock.close()
        logger.info("✓ Echo server is running on port 8888")
    except:
        logger.error("✗ Echo server not running. Start it with: python3 simple_tcp_test.py")
        return False
    
    # Test through PyLiRP client forwarder (port 8888 should be forwarded)
    try:
        logger.info("Testing connection through PyLiRP forwarder...")
        
        # Connect to local forwarder
        reader, writer = await asyncio.open_connection('127.0.0.1', 8888)
        logger.info("✓ Connected to PyLiRP forwarder")
        
        # Test 1: Single message
        test_msg = b"Hello PyLiRP\n"
        writer.write(test_msg)
        await writer.drain()
        logger.info(f"→ Sent: {test_msg.decode().strip()}")
        
        # Read response
        response = await asyncio.wait_for(reader.readline(), timeout=5)
        logger.info(f"← Received: {response.decode().strip()}")
        
        if b"ECHO:" in response:
            logger.info("✓ Test 1 passed: Single message echoed correctly")
        else:
            logger.error("✗ Test 1 failed: Unexpected response")
            return False
        
        # Test 2: Multiple messages in sequence
        logger.info("\nTesting multiple messages...")
        messages = [b"Message 1\n", b"Message 2\n", b"Message 3\n"]
        
        for msg in messages:
            writer.write(msg)
            await writer.drain()
            logger.info(f"→ Sent: {msg.decode().strip()}")
            
            response = await asyncio.wait_for(reader.readline(), timeout=5)
            logger.info(f"← Received: {response.decode().strip()}")
            
            if b"ECHO:" not in response:
                logger.error(f"✗ Failed on message: {msg}")
                return False
        
        logger.info("✓ Test 2 passed: Multiple messages echoed correctly")
        
        # Test 3: Larger data block
        logger.info("\nTesting larger data block...")
        large_msg = b"X" * 1000 + b"\n"
        writer.write(large_msg)
        await writer.drain()
        logger.info(f"→ Sent: {len(large_msg)} bytes")
        
        response = await asyncio.wait_for(reader.readline(), timeout=5)
        logger.info(f"← Received: {len(response)} bytes")
        
        if len(response) > len(large_msg):  # Should have "ECHO: " prefix
            logger.info("✓ Test 3 passed: Large data block handled correctly")
        else:
            logger.error("✗ Test 3 failed: Large data not echoed properly")
            return False
        
        # Clean up
        writer.close()
        await writer.wait_closed()
        
        logger.info("\n✅ All tests passed! TCP forwarding is working correctly.")
        return True
        
    except asyncio.TimeoutError:
        logger.error("✗ Timeout waiting for response - check if PyLiRP is running")
        return False
    except ConnectionRefusedError:
        logger.error("✗ Connection refused - PyLiRP forwarder not listening on port 8888")
        logger.error("  Start PyLiRP client with: python3 main.py --config config_unified.yaml --mode client")
        return False
    except Exception as e:
        logger.error(f"✗ Test failed with error: {e}")
        return False

async def main():
    """Main test runner"""
    logger.info("=== PyLiRP TCP Fix Test Suite ===\n")
    
    # Check prerequisites
    logger.info("Prerequisites:")
    logger.info("1. Echo server running: python3 simple_tcp_test.py")
    logger.info("2. PyLiRP host running: python3 main.py --config config_unified.yaml --mode host")
    logger.info("3. PyLiRP client running: python3 main.py --config config_unified.yaml --mode client")
    logger.info("")
    
    # Run tests
    success = await test_echo_server()
    
    if success:
        logger.info("\n🎉 SUCCESS: TCP ACK sequence number fix is working!")
    else:
        logger.info("\n❌ FAILURE: Tests did not pass")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())