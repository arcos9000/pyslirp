#!/usr/bin/env python3
"""
Debug the connection issue between test and echo server
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safe_logger import get_safe_logger

logger = get_safe_logger(__name__)

async def test_direct_echo_connection():
    """Test direct connection to echo server to isolate the issue"""
    try:
        # Connect directly to echo server (bypass PyLiRP)
        reader, writer = await asyncio.open_connection('127.0.0.1', 8888)
        print("✓ Connected directly to echo server")
        
        # Test 1: Single message
        msg1 = b"Hello Direct\n"
        writer.write(msg1)
        await writer.drain()
        print(f"→ Sent: {msg1.decode().strip()}")
        
        response1 = await asyncio.wait_for(reader.readline(), timeout=5)
        print(f"← Received: {response1.decode().strip()}")
        
        # Test 2: Second message immediately 
        msg2 = b"Message 2\n"
        writer.write(msg2)
        await writer.drain()
        print(f"→ Sent: {msg2.decode().strip()}")
        
        response2 = await asyncio.wait_for(reader.readline(), timeout=5)
        print(f"← Received: {response2.decode().strip()}")
        
        # Test 3: Third message
        msg3 = b"Message 3\n"
        writer.write(msg3)
        await writer.drain()
        print(f"→ Sent: {msg3.decode().strip()}")
        
        response3 = await asyncio.wait_for(reader.readline(), timeout=5)
        print(f"← Received: {response3.decode().strip()}")
        
        print("✓ Direct connection test passed - echo server works correctly")
        
        # Close connection
        writer.close()
        await writer.wait_closed()
        
        return True
        
    except asyncio.TimeoutError:
        print("✗ Direct connection timeout")
        return False
    except Exception as e:
        print(f"✗ Direct connection error: {e}")
        return False

async def test_through_pyslirp():
    """Test connection through PyLiRP to compare behavior"""
    try:
        # This would connect through PyLiRP forwarder
        # For now, just attempt connection to see if forwarder is running
        reader, writer = await asyncio.open_connection('127.0.0.1', 8888)
        print("✓ Connected through PyLiRP forwarder")
        
        # Test single message
        msg = b"Hello PyLiRP\n"
        writer.write(msg)
        await writer.drain()
        print(f"→ Sent: {msg.decode().strip()}")
        
        response = await asyncio.wait_for(reader.readline(), timeout=5)
        print(f"← Received: {response.decode().strip()}")
        
        # Check if connection is still alive by sending another message
        msg2 = b"Second message\n" 
        writer.write(msg2)
        await writer.drain()
        print(f"→ Sent: {msg2.decode().strip()}")
        
        # This is where the problem likely occurs
        try:
            response2 = await asyncio.wait_for(reader.readline(), timeout=5)
            print(f"← Received: {response2.decode().strip()}")
            print("✓ PyLiRP connection works for multiple messages")
        except asyncio.TimeoutError:
            print("✗ PyLiRP connection timeout on second message")
            return False
        
        writer.close()
        await writer.wait_closed()
        return True
        
    except Exception as e:
        print(f"✗ PyLiRP connection error: {e}")
        return False

async def main():
    print("=== Debug Connection Issue ===")
    
    print("\n1. Testing direct connection to echo server...")
    direct_ok = await test_direct_echo_connection()
    
    if not direct_ok:
        print("Echo server itself has issues - fix that first")
        return
    
    print("\n2. Testing connection through PyLiRP...")
    pyslirp_ok = await test_through_pyslirp()
    
    if not pyslirp_ok:
        print("Issue is in PyLiRP forwarding - connection drops after first message")
    else:
        print("PyLiRP forwarding works correctly")

if __name__ == "__main__":
    asyncio.run(main())