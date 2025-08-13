#!/usr/bin/env python3
"""
Simple debug test with logging enabled
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safe_logger import setup_safe_logging

async def test_connection():
    """Test connection with logging enabled"""
    try:
        # Connect to PyLiRP forwarder
        reader, writer = await asyncio.open_connection('127.0.0.1', 8888)
        print("✓ Connected to PyLiRP forwarder")
        
        # Send first message
        msg1 = b"Hello PyLiRP\n"
        writer.write(msg1)
        await writer.drain()
        print(f"→ Sent: {msg1.decode().strip()}")
        
        response1 = await asyncio.wait_for(reader.readline(), timeout=10)
        print(f"← Received: {response1.decode().strip()}")
        
        # Wait a moment
        await asyncio.sleep(1)
        
        # Send second message  
        msg2 = b"Second message\n"
        writer.write(msg2)
        await writer.drain()
        print(f"→ Sent: {msg2.decode().strip()}")
        
        # This should fail with current bug
        response2 = await asyncio.wait_for(reader.readline(), timeout=10)
        print(f"← Received: {response2.decode().strip()}")
        
        writer.close()
        await writer.wait_closed()
        print("✓ Connection test completed successfully")
        
    except asyncio.TimeoutError:
        print("✗ Timeout waiting for response")
    except Exception as e:
        print(f"✗ Connection error: {e}")

if __name__ == "__main__":
    # Enable logging for debug output
    setup_safe_logging(enabled=True)
    asyncio.run(test_connection())