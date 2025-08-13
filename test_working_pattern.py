#!/usr/bin/env python3
"""
Test the working stream relay pattern
"""

import asyncio
from safe_logger import setup_safe_logging, get_safe_logger

setup_safe_logging(enabled=True)
logger = get_safe_logger(__name__)

async def relay_streams(reader1, writer1, reader2, writer2):
    """Standard working pattern - bidirectional stream relay"""
    
    async def forward(from_reader, to_writer, name):
        try:
            while True:
                data = await from_reader.read(4096)
                if not data:
                    logger.info(f"{name}: Connection closed")
                    break
                to_writer.write(data)
                await to_writer.drain()
                logger.info(f"{name}: Forwarded {len(data)} bytes")
        except Exception as e:
            logger.info(f"{name}: Error {e}")
        finally:
            to_writer.close()
    
    # Both directions simultaneously - THE WORKING PATTERN
    await asyncio.gather(
        forward(reader1, writer2, "Direction1"),
        forward(reader2, writer1, "Direction2"),
        return_exceptions=True
    )

async def handle_connection(reader, writer):
    """Handle proxy connection using working pattern"""
    try:
        # Connect to echo server
        target_reader, target_writer = await asyncio.open_connection('127.0.0.1', 8888)
        logger.info("Connected to echo server")
        
        # Use standard working pattern
        await relay_streams(reader, writer, target_reader, target_writer)
        
    except Exception as e:
        logger.error(f"Proxy error: {e}")

async def test_working_proxy():
    """Test that the standard pattern actually works"""
    
    # Start echo server
    async def echo_handler(reader, writer):
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                response = b"ECHO: " + data
                writer.write(response)
                await writer.drain()
        except:
            pass
        finally:
            writer.close()
    
    echo_server = await asyncio.start_server(echo_handler, '127.0.0.1', 8888)
    logger.info("Echo server started on port 8888")
    
    # Start proxy server
    proxy_server = await asyncio.start_server(handle_connection, '127.0.0.1', 9999)
    logger.info("Proxy server started on port 9999")
    
    async with echo_server, proxy_server:
        # Test the proxy
        logger.info("Testing proxy...")
        
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', 9999)
            
            # Send multiple messages
            for i in range(3):
                msg = f"Message {i+1}\n".encode()
                writer.write(msg)
                await writer.drain()
                logger.info(f"Sent: {msg.decode().strip()}")
                
                response = await asyncio.wait_for(reader.readline(), timeout=5)
                logger.info(f"Received: {response.decode().strip()}")
                
                if not response.startswith(b"ECHO:"):
                    logger.error("Wrong response!")
                    return False
            
            writer.close()
            logger.info("✅ WORKING PATTERN TEST PASSED!")
            return True
            
        except Exception as e:
            logger.error(f"Test failed: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(test_working_proxy())