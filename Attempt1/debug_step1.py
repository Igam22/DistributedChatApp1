#!/usr/bin/env python3
"""
Step 1: Debug single server startup
This script will help us understand what happens when starting one server alone.
"""

import socket
import time
from resources.utils import safe_print

def test_single_server():
    """Test what happens when starting a single server"""
    
    safe_print("=== STEP 1: SINGLE SERVER DEBUG ===")
    safe_print("Testing single server startup...")
    
    # Test basic imports
    try:
        from resources.utils import group_view_servers, group_view_clients
        from resources.utils import MULTICAST_GROUP_ADDRESS, server_last_seen
        safe_print("✅ Basic imports successful")
    except Exception as e:
        safe_print(f"❌ Import error: {e}")
        return False
    
    # Test server ID generation
    try:
        from resources.utils import generate_server_id
        server_ip = socket.gethostbyname(socket.gethostname())
        hostname = socket.gethostname()
        server_id = generate_server_id(server_ip, hostname)
        safe_print(f"✅ Server ID generated: {server_id}")
        safe_print(f"   IP: {server_ip}, Hostname: {hostname}")
    except Exception as e:
        safe_print(f"❌ Server ID generation error: {e}")
        return False
    
    # Test fault tolerance initialization
    try:
        from FaultTolerance import initialize_fault_tolerance
        ft_manager = initialize_fault_tolerance(str(server_id), "server")
        safe_print("✅ Fault tolerance initialized")
    except Exception as e:
        safe_print(f"❌ Fault tolerance error: {e}")
        safe_print("   This might be causing issues...")
        return False
    
    # Test multicast socket creation
    try:
        from resources.utils import MULTICAST_IP, MULTICAST_PORT
        UDP_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        UDP_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        UDP_socket.bind(('', MULTICAST_PORT))
        
        # Join multicast group
        import struct
        mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_IP), socket.INADDR_ANY)
        UDP_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        safe_print("✅ Multicast socket created successfully")
        UDP_socket.close()
    except Exception as e:
        safe_print(f"❌ Multicast socket error: {e}")
        safe_print("   This could prevent communication...")
        return False
    
    # Test group view initialization
    try:
        from GroupView import start_group_view, get_group_view
        start_group_view()
        group_view = get_group_view()
        safe_print("✅ Group view initialized")
    except Exception as e:
        safe_print(f"❌ Group view error: {e}")
        return False
    
    safe_print("=== STEP 1 RESULTS ===")
    safe_print("Single server basic components test completed.")
    safe_print("If all tests passed, the issue is likely in server-to-server communication.")
    
    return True

if __name__ == "__main__":
    success = test_single_server()
    if success:
        safe_print("\n🟢 Step 1 PASSED - Basic components work")
        safe_print("Next: Run 'python debug_step2.py' to test server communication")
    else:
        safe_print("\n🔴 Step 1 FAILED - Fix basic components first")