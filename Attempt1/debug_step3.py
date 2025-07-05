#!/usr/bin/env python3
"""
Step 3: Debug the exact startup sequence that causes your errors
This reproduces the actual server startup sequence to find the issue.
"""

import socket
import time
import threading
import sys
from resources.utils import safe_print

def debug_server_startup():
    """Debug the exact server startup sequence"""
    
    safe_print("=== STEP 3: REPRODUCING ACTUAL SERVER STARTUP ===")
    safe_print("This will reproduce the exact sequence that causes your errors...")
    
    try:
        # Import everything like Server.py does
        from resources.utils import group_view_servers, group_view_clients, server_last_seen
        from resources.utils import MULTICAST_GROUP_ADDRESS, generate_server_id
        from LeaderElection import initialize_election, trigger_election
        from GroupView import get_group_view, start_group_view
        from DiscoveryManager import DiscoveryManager  
        from FaultTolerance import initialize_fault_tolerance, get_fault_tolerance_manager
        
        safe_print("✅ All imports successful")
        
        # Generate server ID like Server.py does
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
        server_id = generate_server_id(server_ip, hostname)
        
        safe_print(f"✅ Server info: IP={server_ip}, Hostname={hostname}, ID={server_id}")
        
        # Initialize unified group view
        start_group_view()
        group_view = get_group_view()
        safe_print("✅ Group view started")
        
        # Initialize fault tolerance system (this is where issues might start)
        safe_print("Initializing fault tolerance...")
        ft_manager = initialize_fault_tolerance(str(server_id), "server")
        safe_print("✅ Fault tolerance initialized")
        
        # Add this server to group views
        group_view_servers.add(server_id)
        server_last_seen[server_id] = time.time()
        group_view.add_participant(str(server_id), 'server', (server_ip, 0), hostname)
        safe_print("✅ Server added to group views")
        
        # Start fault tolerance (this starts partition detection)
        safe_print("Starting fault tolerance manager...")
        ft_manager.start()
        safe_print("✅ Fault tolerance started")
        
        # Test if we can process a SERVER_ALIVE message like the real server would
        safe_print("Testing SERVER_ALIVE message processing...")
        test_message = f"SERVER_ALIVE:{server_ip}:{hostname}"
        test_addr = (server_ip, 12345)
        
        # This is what causes your "corrupted message" error
        result = ft_manager.handle_message(test_message, test_addr)
        safe_print(f"✅ Message processing result: {result}")
        
        # Let it run for a few seconds to see if partition detection triggers
        safe_print("Running for 5 seconds to observe partition detection...")
        time.sleep(5)
        
        # Stop fault tolerance
        ft_manager.stop()
        safe_print("✅ Fault tolerance stopped")
        
    except Exception as e:
        safe_print(f"❌ Error during startup sequence: {e}")
        import traceback
        safe_print(f"Full traceback: {traceback.format_exc()}")
        return False
    
    safe_print("=== STEP 3 RESULTS ===")
    safe_print("Server startup sequence completed without major errors.")
    return True

if __name__ == "__main__":
    success = debug_server_startup()
    if success:
        safe_print("\n🟢 Step 3 PASSED - Basic startup works")
        safe_print("The issue might be in multi-server communication timing")
    else:
        safe_print("\n🔴 Step 3 FAILED - Found the startup issue!")