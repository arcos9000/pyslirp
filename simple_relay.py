#!/usr/bin/env python3
"""
Simple TCP Stream Relay - The Standard Solution

This implements TCP forwarding the way every working proxy does it:
Just relay streams bidirectionally without parsing TCP packets.
"""

import asyncio
import socket
from safe_logger import get_safe_logger

logger = get_safe_logger(__name__)

class StreamRelay:
    """Simple bidirectional stream relay - the standard pattern"""
    
    def __init__(self, listen_port=8888, target_host='127.0.0.1', target_port=8888):
        self.listen_port = listen_port
        self.target_host = target_host  
        self.target_port = target_port
        
    async def handle_client(self, client_reader: asyncio.StreamReader, 
                          client_writer: asyncio.StreamWriter):
        """Handle incoming client connection with standard relay pattern"""
        client_addr = client_writer.get_extra_info('peername')
        logger.info(f"Client connected from {client_addr}")
        
        try:
            # Connect to target service
            target_reader, target_writer = await asyncio.open_connection(
                self.target_host, self.target_port
            )
            logger.info(f"Connected to target {self.target_host}:{self.target_port}")
            
            # Start bidirectional relay using the standard pattern
            await self._relay_streams(
                client_reader, client_writer,
                target_reader, target_writer
            )
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            logger.info(f"Client {client_addr} disconnected")
    
    async def _relay_streams(self, reader1, writer1, reader2, writer2):
        """
        Standard bidirectional stream relay pattern used by all working proxies.
        This is the correct way to do TCP forwarding.
        """
        async def forward_stream(from_reader, to_writer, direction):
            """Forward data in one direction"""
            try:
                while True:
                    # Read data (standard 4KB chunks)
                    data = await from_reader.read(4096)
                    if not data:
                        logger.debug(f"{direction}: Stream closed")
                        break
                        
                    # Write data to other side
                    to_writer.write(data)
                    await to_writer.drain()
                    logger.debug(f"{direction}: Forwarded {len(data)} bytes")
                    
            except Exception as e:
                logger.debug(f"{direction}: Forward error: {e}")
            finally:
                # Close the writer when done
                to_writer.close()
                try:
                    await to_writer.wait_closed()
                except:
                    pass
        
        # Run both directions concurrently - THE KEY PATTERN
        await asyncio.gather(
            forward_stream(reader1, writer2, "Client->Target"),
            forward_stream(reader2, writer1, "Target->Client"), 
            return_exceptions=True
        )
    
    async def start_server(self):
        """Start the relay server"""
        server = await asyncio.start_server(
            self.handle_client,
            '127.0.0.1',
            self.listen_port
        )
        
        logger.info(f"Stream relay listening on 127.0.0.1:{self.listen_port}")
        logger.info(f"Forwarding to {self.target_host}:{self.target_port}")
        
        async with server:
            await server.serve_forever()

async def test_simple_relay():
    """Test the simple relay against the echo server"""
    # Start relay that forwards port 9999 -> 8888 (echo server)
    relay = StreamRelay(listen_port=9999, target_host='127.0.0.1', target_port=8888)
    
    # Start relay server in background
    relay_task = asyncio.create_task(relay.start_server())
    
    # Give it a moment to start
    await asyncio.sleep(0.5)
    
    try:
        # Test the relay
        logger.info("Testing simple relay...")
        
        # Connect to relay (not directly to echo server)
        reader, writer = await asyncio.open_connection('127.0.0.1', 9999)
        logger.info("Connected to relay")
        
        # Test multiple messages
        messages = [b"Hello World\n", b"Message 2\n", b"Message 3\n"]
        
        for i, msg in enumerate(messages):
            writer.write(msg)
            await writer.drain()
            logger.info(f"Sent: {msg.decode().strip()}")
            
            response = await asyncio.wait_for(reader.readline(), timeout=5)
            logger.info(f"Received: {response.decode().strip()}")
            
            if not response.startswith(b"ECHO:"):
                logger.error(f"Unexpected response: {response}")
                return False
        
        writer.close()
        await writer.wait_closed()
        
        logger.info("✅ Simple relay test passed!")
        return True
        
    except Exception as e:
        logger.error(f"Relay test failed: {e}")
        return False
    finally:
        relay_task.cancel()
        try:
            await relay_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    # Enable logging for test
    from safe_logger import setup_safe_logging
    setup_safe_logging(enabled=True)
    
    # This demonstrates the standard working pattern
    asyncio.run(test_simple_relay())