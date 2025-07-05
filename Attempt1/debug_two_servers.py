#!/usr/bin/env python3
"""
Debug script to simulate two servers communicating
Run this to see what happens when two servers discover each other
"""

import socket
import time
import threading
from resources.utils import safe_print

def simulate_two_servers():
    """Simulate the communication between two servers"""
    
    safe_print("=== SIMULATING TWO SERVER COMMUNICATION ===")
    
    # Get current machine info
    def getIP():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(('10.254.254.254', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP
    
    server_ip = getIP()
    hostname = socket.gethostname()
    
    from resources.utils import generate_server_id
    server_id_1 = generate_server_id(server_ip, hostname)
    
    # Simulate a second server with different ID
    server_id_2 = generate_server_id("192.168.178.37", "LAPTOP-G06A5UHA")  # From your error
    
    safe_print(f"Server 1: ID={server_id_1}, IP={server_ip}, Host={hostname}")
    safe_print(f"Server 2: ID={server_id_2}, IP=192.168.178.37, Host=LAPTOP-G06A5UHA")
    
    # Test what happens when Server 1 processes a message from Server 2
    try:
        from FaultTolerance import initialize_fault_tolerance
        
        # Initialize fault tolerance for Server 1
        ft_manager_1 = initialize_fault_tolerance(str(server_id_1), "server")
        ft_manager_1.start()
        
        safe_print("✅ Server 1 fault tolerance started")
        
        # Add Server 2 to known nodes (this is what happens during discovery)
        ft_manager_1.partition_detector.add_known_node(str(server_id_2))
        safe_print(f"✅ Server 1 added Server 2 ({server_id_2}) to known nodes")
        
        # Simulate Server 2 sending SERVER_ALIVE message to Server 1
        server_2_message = "SERVER_ALIVE:192.168.178.37:LAPTOP-G06A5UHA"
        server_2_addr = ('192.168.178.37', 59144)  # From your error
        
        safe_print(f"Testing Server 2 message: {server_2_message}")
        result = ft_manager_1.handle_message(server_2_message, server_2_addr)
        safe_print(f"✅ Server 1 processed Server 2 message: {result}")
        
        # Wait a moment then test partition detection
        safe_print("Waiting 2 seconds, then testing partition detection...")
        time.sleep(2)
        
        # Manually trigger partition detection
        partition_result = ft_manager_1.partition_detector.probe_nodes()
        safe_print(f"Partition detection result: {partition_result}")
        
        # Check if Server 2 is considered reachable
        reachable = ft_manager_1.partition_detector.reachable_nodes
        safe_print(f"Reachable nodes: {reachable}")
        
        ft_manager_1.stop()
        
    except Exception as e:
        safe_print(f"❌ Error in two-server simulation: {e}")
        import traceback
        safe_print(f"Traceback: {traceback.format_exc()}")
        return False
    
    safe_print("=== TWO SERVER SIMULATION COMPLETE ===")
    return True

if __name__ == "__main__":
    simulate_two_servers()