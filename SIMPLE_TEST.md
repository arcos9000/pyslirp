# Simple TCP Test for PyLiRP

This test verifies basic TCP data flow through PPP using a simple echo server instead of complex services like SSH.

## Test Setup

### 1. Start Echo Server
```bash
python3 simple_tcp_test.py
```

This will:
- Start an echo server on `127.0.0.1:8888`
- Test direct connection to verify server works
- Keep server running for PPP tests

### 2. Start PyLiRP on BOTH Machines

**On Host (Server with services):**
```bash
python3 main.py --config config_unified.yaml --mode host
```

**On Client (Initiates connections):**
```bash
python3 main.py --config config_unified.yaml --mode client
```

This uses configuration that:
- Maps PPP port 8888 → local port 8888 (echo server)
- Enables debug logging
- Allows port 8888 in security rules

## Test Procedure

### Step 1: Verify Echo Server Works Directly
Before testing through PPP, verify the echo server works:

```bash
# In another terminal:
telnet 127.0.0.1 8888
```

Type messages - you should see "ECHO: <your_message>" responses.

### Step 2: Test Through PPP
Since 10.0.0.x IPs only exist within PPP and are NOT exposed to the OS, the client creates local listeners:

```bash
# On PPP client machine (after client mode starts):
telnet localhost 8888

# Or for SSH:
ssh localhost -p 2222
```

The client TCP forwarder will:
1. Accept connection on localhost:8888
2. Create TCP connection through PPP to host's 10.0.0.1:8888  
3. Forward data bidirectionally

### Expected Behavior

1. **Connection Establishment**:
   ```
   TCP: SYN from PPP client (10.0.0.2:XXXXX -> 10.0.0.1:8888)  
   TCP: SYN+ACK from server (10.0.0.1:8888 -> 10.0.0.2:XXXXX)
   TCP: ACK from client
   Connection ESTABLISHED
   ```

2. **Data Flow Test**:
   ```
   Client types: "Hello"
   Expected: Server responds "ECHO: Hello"
   ```

3. **Bidirectional Flow**:
   - Client → PPP → Server → Echo Server: "Hello"
   - Echo Server → Server → PPP → Client: "ECHO: Hello"

## Debug Information

The test will show detailed logging:

```
INFO - Bidirectional forwarding established for XXXXX->8888
INFO - Starting bidirectional forwarding: PPP(XXXXX) <-> Service(8888)  
INFO - TCP: ESTABLISHED state - received 5 bytes in sequence
DEBUG - Queued 5 bytes for forwarding
DEBUG - Forwarded 5 bytes PPP -> Service
INFO - Echo server: Received 5 bytes: b'Hello'
INFO - Echo server: Sent 11 bytes back to client
DEBUG - Forwarded 11 bytes Service -> PPP
```

## Troubleshooting

### If Direct Connection Fails
- Check if port 8888 is already in use: `netstat -tlnp | grep 8888`
- Try different port in both `simple_tcp_test.py` and `config_simple_test.yaml`

### If PPP Connection Fails  
- Verify PPP negotiation completed: Look for "IP layer ready"
- Check service mapping: Look for "Establishing bidirectional forwarding to 127.0.0.1:8888"
- Verify port is allowed: Check security logs

### If Data Doesn't Flow
- Look for "Queued X bytes for forwarding" messages
- Check bidirectional tasks are running: "Starting PPP -> Service forwarding"
- Monitor echo server logs for received data

## Success Criteria

✅ **Test passes if:**
1. Direct connection to echo server works
2. PPP connection to 10.0.0.1:8888 establishes  
3. Data sent through PPP gets echoed back correctly
4. Both directions show data forwarding in logs

❌ **Test fails if:**
- Connection times out
- Data is sent but no response received  
- Server receives data but client doesn't get response
- Any exceptions in bidirectional forwarding tasks