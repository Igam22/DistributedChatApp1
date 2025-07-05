# Distributed Chat System Testing Instructions

## Overview
This document provides comprehensive instructions for testing the distributed chat system across multiple computers and network configurations.

## System Requirements

### Software Requirements
- Python 3.7 or higher
- Network connectivity between test machines
- Same network subnet for multicast communication (recommended)

### Network Requirements
- UDP multicast support (most networks support this)
- Port 5008 must be available and not blocked by firewalls
- Multicast address 224.1.1.1 must be accessible

## Pre-Testing Setup

### 1. File Distribution
Copy the entire project directory to each test machine:
```bash
# Copy these files to each computer:
- Server.py
- Client.py
- MulticastReceiver.py
- LeaderElection.py
- GroupView.py
- DiscoveryManager.py
- FaultTolerance.py
- BullyElection.py (legacy support)
- resources/utils.py
```

### 2. Network Configuration Check
On each machine, verify network connectivity:

```bash
# Check IP address
python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 80))
print('IP Address:', s.getsockname()[0])
s.close()
"

# Test multicast capability (run on one machine)
python3 -c "
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
sock.sendto(b'test', ('224.1.1.1', 5008))
print('Multicast test sent')
sock.close()
"
```

### 3. Firewall Configuration
Ensure UDP port 5008 is open:

**Windows:**
```cmd
netsh advfirewall firewall add rule name="DistributedChat" dir=in action=allow protocol=UDP localport=5008
```

**Linux/macOS:**
```bash
# Usually no action needed, but check with:
sudo ufw allow 5008/udp  # Ubuntu
# or
sudo firewall-cmd --add-port=5008/udp --permanent  # CentOS/RHEL
```

## Testing Scenarios

### Scenario 1: Basic Two-Machine Setup

**Machine A (First Server):**
```bash
# Terminal 1: Start the multicast receiver
python3 MulticastReceiver.py

# Terminal 2: Start the server
python3 Server.py
```

**Machine B (Second Server):**
```bash
# Wait 10 seconds after Machine A starts

# Terminal 1: Start the multicast receiver
python3 MulticastReceiver.py

# Terminal 2: Start the server
python3 Server.py
```

**Expected Results:**
- Machine A should be elected as leader (lower server ID)
- Machine B should discover Machine A and participate in election
- Both servers should show each other in their group view
- Leader election should complete within 30 seconds

### Scenario 2: Client Connection Testing

**Any Machine (Client):**
```bash
# Connect with default username
python3 Client.py

# Or connect with specific username
python3 Client.py Alice
```

**Expected Results:**
- Client should discover available servers within 15 seconds
- Client should receive leader information
- Client should appear in server group views
- Client heartbeat should be visible in server logs

### Scenario 3: Leader Failure Testing

**Steps:**
1. Start 3 servers (A, B, C) on different machines
2. Wait for leader election to complete
3. Note which server is the leader
4. Terminate the leader server (Ctrl+C)
5. Observe new leader election

**Expected Results:**
- Remaining servers should detect leader failure within 15 seconds
- New election should start automatically
- New leader should be elected within 30 seconds
- Clients should receive updated leader information

### Scenario 4: Network Partition Testing

**Setup:**
1. Start servers on machines A, B, C
2. Use network tools to simulate partition

**Network Partition Simulation:**
```bash
# On Linux, block traffic to specific IP
sudo iptables -A INPUT -s [OTHER_MACHINE_IP] -j DROP
sudo iptables -A OUTPUT -d [OTHER_MACHINE_IP] -j DROP

# To restore connection
sudo iptables -F
```

**Expected Results:**
- Servers should detect partition within 10 seconds
- Each partition should elect its own leader
- When partition heals, unified leader election should occur

### Scenario 5: Dynamic Discovery Testing

**Steps:**
1. Start server A
2. Wait 30 seconds
3. Start server B
4. Wait 30 seconds  
5. Start server C
6. Connect client from different machine

**Expected Results:**
- Each new server should be discovered by existing servers
- Leader election should occur each time a new server joins
- Client should discover all available servers

## Monitoring and Diagnostics

### 1. Real-time System Status
While servers are running, send status requests:
```bash
# From any machine, send status message
python3 -c "
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(b'status', ('224.1.1.1', 5008))
sock.close()
"
```

### 2. Server Logs Analysis
Monitor server output for:
- Discovery messages: "Discovered server: ..."
- Election messages: "Server X starting election"
- Leader announcements: "Server X is now the leader"
- Fault tolerance events: "Node X failed", "Partition detected"

### 3. Network Traffic Monitoring
Use network tools to monitor multicast traffic:
```bash
# Linux
sudo tcpdump -i any -n 'dst 224.1.1.1 and port 5008'

# Wireshark filter
udp.port == 5008 and ip.dst == 224.1.1.1
```

## Common Issues and Solutions

### Issue 1: Multicast Not Working
**Symptoms:** Servers can't discover each other
**Solutions:**
- Check if machines are on same subnet
- Verify multicast routing is enabled
- Try increasing TTL value in utils.py
- Test with ping: `ping 224.1.1.1`

### Issue 2: Election Storms
**Symptoms:** Continuous leader elections
**Solutions:**
- Check system clock synchronization
- Verify unique server IDs
- Check for network packet loss

### Issue 3: Client Connection Failures
**Symptoms:** Clients can't connect to servers
**Solutions:**
- Ensure at least one server is running
- Check client retry attempts in logs
- Verify server announces are being sent

### Issue 4: Split-Brain Scenarios
**Symptoms:** Multiple leaders in different partitions
**Solutions:**
- This is expected behavior during partitions
- Leaders should merge when partition heals
- Check partition detection logs

## Performance Testing

### 1. Load Testing
```bash
# Start multiple clients simultaneously
for i in {1..10}; do
    python3 Client.py "User$i" &
done
```

### 2. Failure Recovery Testing
```bash
# Script to test leader failure recovery
#!/bin/bash
for i in {1..5}; do
    echo "Test $i: Starting servers..."
    python3 Server.py &
    SERVER_PID=$!
    sleep 30
    echo "Killing leader..."
    kill $SERVER_PID
    sleep 20
    echo "Test $i completed"
done
```

## Success Criteria

### Basic Functionality
- [ ] Servers discover each other within 30 seconds
- [ ] Leader election completes within 30 seconds
- [ ] Clients can connect and communicate
- [ ] System status shows all participants

### Fault Tolerance
- [ ] Leader failure triggers new election within 15 seconds
- [ ] Network partitions are detected and handled
- [ ] Clients automatically reconnect after server failures
- [ ] Message delivery is reliable with retries

### Scalability
- [ ] System works with 3+ servers
- [ ] Multiple clients can connect simultaneously
- [ ] Performance remains stable under load

## Troubleshooting Commands

```bash
# Check Python version
python3 --version

# Test socket permissions
python3 -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(('', 5008)); print('Port 5008 available')"

# Check multicast group membership
netstat -g  # Linux
netstat -gn  # macOS

# Monitor system resources
top  # or htop on Linux
```

## Expected Output Examples

### Successful Server Startup
```
Server startup complete with fault tolerance enabled
Discovery statistics:
  discovery_phase: STARTUP
  discovery_complete: True
  discovered_servers_count: 2

Fault tolerance statistics:
  fault_counts: {'crash': 0, 'omission': 0, 'byzantine': 0, 'partition': 0}
  
UNIFIED GROUP VIEW:
Servers: 3, Clients: 2, Leader: ServerA (ID: 1234)
```

### Successful Client Connection
```
Client discovery attempt 1/3
Successfully connected to distributed chat system
Welcome Alice_1234abcd! Current Leader: ServerA (ID: 1234)

Alice> Hello, world!
Server response: Your message was received by ServerA!
```

This testing guide should help you thoroughly validate the distributed chat system across multiple machines and network conditions.