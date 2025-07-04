import socket
import threading
import time
from resources.utils import group_view_servers
from resources.utils import group_view_clients
from resources.utils import server_last_seen
from resources.utils import MULTICAST_GROUP_ADDRESS
from LeaderElection import initialize_election, trigger_election, detect_leader_failure, get_current_leader
from GroupView import get_group_view, start_group_view, print_system_status
from DiscoveryManager import DiscoveryManager
from FaultTolerance import initialize_fault_tolerance, get_fault_tolerance_manager

# Getting the IP address by trying to reach unreachable address, method from:https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib 
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

# Server Configuration and Initialization
server_ip = getIP()  # Get this server's IP address
hostname = socket.gethostname()  # Get this server's hostname

# Import standardized utilities
from resources.utils import (generate_server_id, SERVER_TIMEOUT, HEARTBEAT_INTERVAL, 
                            CLEANUP_INTERVAL, SERVER_ANNOUNCE_INTERVAL, create_multicast_socket)

# Generate consistent server ID using standardized function
server_id = generate_server_id(server_ip, hostname) 






def announce_server():
    """
    Continuously announce this server's presence to other nodes in the system.
    This helps with dynamic discovery when new servers join the network.
    """
    # Create a multicast socket for sending announcements
    announce_socket = create_multicast_socket()
    
    while True:
        try:
            # Create standardized server announcement message
            server_announcement = f"SERVER_ALIVE:{server_ip}:{hostname}"
            announce_socket.sendto(server_announcement.encode(), MULTICAST_GROUP_ADDRESS)
            
            # Wait for the next announcement interval
            time.sleep(SERVER_ANNOUNCE_INTERVAL)
            
        except Exception as e:
            print(f"Error in server announcement: {e}")
            time.sleep(SERVER_ANNOUNCE_INTERVAL)  # Continue despite errors

def probe_servers():
    """
    Actively probe for other servers in the network.
    This is a legacy function that works alongside the enhanced DiscoveryManager.
    """
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe_socket.settimeout(2)
    
    # Send probe message with our server details
    probe_msg = f"SERVER_PROBE:{server_ip}:{server_id}"
    probe_socket.sendto(probe_msg.encode(), MULTICAST_GROUP_ADDRESS)
    
    # Listen for responses
    try:
        while True:
            data, addr = probe_socket.recvfrom(1024)
            response = data.decode()
            if response.startswith("SERVER_RESPONSE:"):
                # Parse the response to get server details
                parts = response.split(":")
                if len(parts) >= 3:
                    response_hostname = parts[1]
                    response_ip = parts[2]
                    response_server_id = generate_server_id(response_ip, response_hostname)
                    
                    # Don't add ourselves
                    if response_server_id != server_id:
                        group_view_servers.add(response_server_id)
                        server_last_seen[response_server_id] = time.time()
                        print(f"Probe discovered server: {response_hostname} (ID: {response_server_id})")
    except socket.timeout:
        pass  # Normal timeout, no more responses
    except Exception as e:
        print(f"Error during server probing: {e}")
    finally:
        probe_socket.close()

def cleanup_dead_servers():
    """
    Remove servers that haven't been seen recently.
    This function ensures we don't remove ourselves from the group view.
    """
    current_time = time.time()
    dead_servers = []
    
    for server_check_id in list(group_view_servers):
        # Never remove ourselves from the group view
        if server_check_id == server_id:
            continue
            
        # Check if other servers have timed out
        if current_time - server_last_seen.get(server_check_id, 0) > SERVER_TIMEOUT:
            dead_servers.append(server_check_id)
    
    # Remove dead servers
    for dead_server_id in dead_servers:
        group_view_servers.discard(dead_server_id)
        server_last_seen.pop(dead_server_id, None)
        print(f"Removed dead server: {dead_server_id}")
        
        # Check if leader failed and trigger election
        detect_leader_failure()

def start_server_discovery():
    """Start server discovery thread"""
    discovery_thread = threading.Thread(target=announce_server, daemon=True)
    discovery_thread.start()
    
    # Start cleanup thread that runs periodically
    def cleanup_loop():
        while True:
            time.sleep(15)
            cleanup_dead_servers()
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

def showSystemcomponents():
    print(f'Servers in System: {group_view_servers}')
    print(f'Leading Server: {get_current_leader()}')
    print(f'Clients in System: {group_view_clients}')
    
    # Also show unified group view
    print("\n" + "="*30)
    print("UNIFIED GROUP VIEW:")
    print_system_status()
    

if __name__ == '__main__':
    # Initialize unified group view
    start_group_view()
    group_view = get_group_view()
    
    # Initialize fault tolerance system
    ft_manager = initialize_fault_tolerance(str(server_id), "server")
    
    # Add fault tolerance recovery callbacks
    def on_crash_recovery(failed_node_id):
        print(f"Server crash detected: {failed_node_id}")
        if str(failed_node_id) == str(get_current_leader()):
            print("Leader crashed, triggering election")
            trigger_election()
        # Remove from group views
        if int(failed_node_id) in group_view_servers:
            group_view_servers.discard(int(failed_node_id))
        group_view.remove_participant(str(failed_node_id))
    
    def on_partition_recovery(partition_detector):
        total_known_nodes = len(partition_detector.known_nodes)
        reachable_nodes = len(partition_detector.reachable_nodes)
        
        # Only process partition events if we have multiple nodes in the system
        if total_known_nodes > 1:
            if partition_detector.in_partition:
                print(f"⚠️  Network partition detected! Reachable: {reachable_nodes}/{total_known_nodes}")
                print("   Entering partition mode - pausing leader election until healed")
            else:
                print(f"✅ Network partition healed! Reachable: {reachable_nodes}/{total_known_nodes}")
                print("   Resuming normal operation and triggering leader election")
                trigger_election()
    
    ft_manager.register_recovery_callback('crash', on_crash_recovery)
    ft_manager.register_recovery_callback('partition', on_partition_recovery)
    
    # Initialize election system
    initialize_election(server_id, server_ip)
    
    # Initialize enhanced discovery manager
    discovery_manager = DiscoveryManager(str(server_id), server_ip, socket.gethostname())
    
    # Add discovery callbacks
    def on_startup_complete():
        print("Discovery startup phase completed")
    
    def on_server_discovered(discovered_server_id):
        # Add to unified group view when server is discovered
        group_view.add_participant(str(discovered_server_id), 'server', ('unknown', 0))
        # Add to fault tolerance manager
        ft_manager.partition_detector.add_known_node(str(discovered_server_id))
    
    discovery_manager.add_discovery_callback('startup_complete', on_startup_complete)
    discovery_manager.add_discovery_callback('server_discovered', on_server_discovered)
    
    # Start legacy discovery for backward compatibility
    start_server_discovery()
    
    # Add this server to the group views
    group_view_servers.add(server_id)
    server_last_seen[server_id] = time.time()
    group_view.add_participant(str(server_id), 'server', (server_ip, 0), socket.gethostname())
    
    # Start fault tolerance
    ft_manager.start()
    
    # Start enhanced discovery (this will handle timing and elections)
    discovery_manager.start_discovery()
    
    print("Server startup complete with fault tolerance enabled")
    print("Discovery statistics:")
    stats = discovery_manager.get_discovery_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\nFault tolerance statistics:")
    ft_stats = ft_manager.get_fault_statistics()
    for key, value in ft_stats.items():
        print(f"  {key}: {value}")
    
    # Wait a bit for initial discovery, then show system status
    time.sleep(5)
    showSystemcomponents()