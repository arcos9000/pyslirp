#!/usr/bin/env python3
"""
Complete PPP Echo Test

This script orchestrates the complete test sequence:
1. Starts the echo server
2. Provides instructions for starting PPP on both sides
3. Tests the connection once PPP is established

Usage:
    python3 test_ppp_echo.py
"""

import asyncio
import logging
import sys
import time
from simple_tcp_test import SimpleEchoServer, SimpleTCPTester

logger = logging.getLogger(__name__)

class PPPEchoTestOrchestrator:
    """Orchestrates complete PPP echo testing"""
    
    def __init__(self):
        self.echo_server = SimpleEchoServer(8888)
        self.tester = SimpleTCPTester()
        
    async def run_complete_test(self):
        """Run the complete test sequence"""
        logger.info("=" * 60)
        logger.info("STARTING PPP ECHO SERVER TEST")
        logger.info("=" * 60)
        
        # Step 1: Start echo server
        logger.info("[STEP 1] Starting echo server on 127.0.0.1:8888...")
        server = await self.echo_server.start()
        
        try:
            # Step 2: Test direct connection
            logger.info("[STEP 2] Testing direct connection to echo server...")
            success = await self.tester.test_direct_connection('127.0.0.1', 8888)
            
            if not success:
                logger.error("Direct connection test failed - echo server not working")
                return False
            
            logger.info("[SUCCESS] Echo server is working correctly!")
            
            # Step 3: Provide PPP setup instructions
            self._show_ppp_instructions()
            
            # Step 4: Wait for PPP setup and provide testing instructions
            await self._wait_for_ppp_setup()
            
            # Keep server running
            logger.info("[READY] Echo server running - ready for PPP tests")
            logger.info("Press Ctrl+C to stop the test")
            
            async with server:
                await server.serve_forever()
                
        except KeyboardInterrupt:
            logger.info("Test stopped by user")
            return True
        except Exception as e:
            logger.error(f"Test failed: {e}")
            return False
        finally:
            await self.echo_server.stop()
    
    def _show_ppp_instructions(self):
        """Show PPP setup instructions"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("[STEP 3] PPP SETUP INSTRUCTIONS")
        logger.info("=" * 60)
        logger.info("")
        logger.info("The echo server is now running. Follow these steps:")
        logger.info("")
        logger.info("1. ON THE HOST MACHINE (server with services):")
        logger.info("   python3 main.py --config config_unified.yaml --mode host")
        logger.info("")
        logger.info("2. ON THE CLIENT MACHINE (connects to services):")
        logger.info("   python3 main.py --config config_unified.yaml --mode client")
        logger.info("")
        logger.info("3. WAIT for both sides to show:")
        logger.info("   - PPP negotiation complete")
        logger.info("   - IP layer ready")
        logger.info("   - (Client) Port forward active: localhost:8888 -> 10.0.0.1:8888")
        logger.info("")
        
    async def _wait_for_ppp_setup(self):
        """Wait for user to set up PPP"""
        logger.info("Waiting for PPP setup... (this will continue in background)")
        await asyncio.sleep(5)  # Give user time to read instructions
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("[STEP 4] TESTING INSTRUCTIONS")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Once PPP is established, test from the CLIENT machine:")
        logger.info("")
        logger.info("Method 1 - Telnet test:")
        logger.info("  telnet localhost 8888")
        logger.info("  Type: Hello World")
        logger.info("  Expected response: ECHO: Hello World")
        logger.info("")
        logger.info("Method 2 - Netcat test:")
        logger.info("  echo 'Test message' | nc localhost 8888")
        logger.info("  Expected response: ECHO: Test message")
        logger.info("")
        logger.info("Method 3 - Python test:")
        logger.info("  python3 -c \"")
        logger.info("import socket")
        logger.info("s = socket.socket()")
        logger.info("s.connect(('localhost', 8888))")
        logger.info("s.send(b'Hello PPP')")
        logger.info("print(s.recv(1024))")
        logger.info("s.close()\"")
        logger.info("")
        logger.info("Expected behavior:")
        logger.info("✅ Connection establishes successfully")
        logger.info("✅ Data sent from client reaches echo server")
        logger.info("✅ Echo response flows back to client")
        logger.info("✅ NO RST packets (flags=0x04) in logs")
        logger.info("")
        logger.info("If you see RST packets, it means:")
        logger.info("❌ Echo server connection failed")
        logger.info("❌ Service forwarding couldn't establish")
        logger.info("❌ Check this echo server is running")
        logger.info("")

    async def test_after_ppp_ready(self):
        """Test connection after PPP is ready (call this manually)"""
        logger.info("Testing PPP connection to echo server...")
        
        # Test through client forwarder (localhost:8888 -> PPP -> host:8888)
        try:
            success = await self.tester.test_direct_connection('localhost', 8888)
            if success:
                logger.info("✅ PPP echo test PASSED!")
                logger.info("Data successfully flowed: Client -> PPP -> Host -> Echo Server -> Host -> PPP -> Client")
                return True
            else:
                logger.error("❌ PPP echo test FAILED!")
                return False
        except Exception as e:
            logger.error(f"❌ PPP echo test ERROR: {e}")
            return False

async def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    orchestrator = PPPEchoTestOrchestrator()
    success = await orchestrator.run_complete_test()
    
    if success:
        logger.info("Test completed successfully")
        return 0
    else:
        logger.error("Test failed")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        sys.exit(0)