import socket
import threading
import time
import sys
import struct
import json

from resources.utils import group_view_servers
from resources.utils import group_view_clients
from resources.utils import server_last_seen
from resources.utils import client_last_seen
from resources.utils import MULTICAST_GROUP_ADDRESS
from resources.utils import MULTICAST_IP
from resources.utils import MULTICAST_PORT
from resources.utils import BUFFER_SIZE
from resources.utils import safe_print
from LeaderElection import initialize_election, trigger_election, detect_leader_failure, get_current_leader, handle_election_message
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
            safe_print(f"Error in server announcement: {e}")
            time.sleep(SERVER_ANNOUNCE_INTERVAL)  # Continue despite errors

def probe_servers():
    """
    Actively probe for other servers in the network.
    This is a legacy function that works alongside the enhanced DiscoveryManager.
    """
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Increased timeout to 5 seconds for better reliability during startup
    probe_socket.settimeout(5)
    
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
                        safe_print(f"Probe discovered server: {response_hostname} (ID: {response_server_id})")
    except socket.timeout:
        pass  # Normal timeout, no more responses
    except Exception as e:
        safe_print(f"Error during server probing: {e}")
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
        safe_print(f"Removed dead server: {dead_server_id}")
        
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

def multicast_receiver():
    """
    Integrated multicast receiver that handles all incoming messages.
    This replaces the functionality of MulticastReceiver.py
    """
    try:
        # Create UDP socket for receiving multicast messages
        UDP_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        UDP_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        UDP_socket.bind(('', MULTICAST_PORT))
        
        # Join multicast group
        mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_IP), socket.INADDR_ANY)
        UDP_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        safe_print(f"Multicast receiver listening on: {MULTICAST_GROUP_ADDRESS}")
        
        while True:
            try:
                data, client_addr = UDP_socket.recvfrom(BUFFER_SIZE)
                msg = data.decode()
                safe_print(f"Received message from {client_addr}: {msg}")
                
                # Handle message with fault tolerance if available
                ft_manager = get_fault_tolerance_manager()
                if ft_manager:
                    processed_msg = ft_manager.handle_message(msg, client_addr)
                    if processed_msg:
                        if processed_msg.get('type') == 'heartbeat_ack':
                            # Send heartbeat acknowledgment
                            response = json.dumps(processed_msg)
                            UDP_socket.sendto(response.encode(), client_addr)
                            continue
                
                response = None
                
                # Handle client join messages
                if msg == "join" or msg.startswith("join:"):
                    if msg.startswith("join:"):
                        parts = msg.split(":")
                        client_id = parts[1] if len(parts) > 1 else f"{client_addr[0]}:{client_addr[1]}"
                    else:
                        client_id = f"{client_addr[0]}:{client_addr[1]}"
                    
                    safe_print(f"\nClient {client_id} at {client_addr} wants to join.")
                    
                    # Add client to legacy view for backward compatibility
                    group_view_clients.add(client_addr)
                    client_last_seen[client_addr] = time.time()
                    
                    # Add client to unified group view
                    group_view = get_group_view()
                    group_view.add_participant(client_id, 'client', client_addr)
                    
                    leader_id = get_current_leader()
                    leader_name = socket.gethostname() if leader_id else "No leader elected"
                    response = f"\nWelcome {client_id}! Current Leader: {leader_name} (ID: {leader_id})"
                
                # Handle server announcements
                elif msg.startswith("SERVER_ALIVE:"):
                    parts = msg.split(":")
                    if len(parts) >= 3:
                        server_ip = parts[1]
                        server_name = parts[2]
                        discovered_server_id = generate_server_id(server_ip, server_name)
                        
                        # Don't process our own announcements
                        if discovered_server_id != server_id:
                            # Add to legacy views for backward compatibility
                            group_view_servers.add(discovered_server_id)
                            server_last_seen[discovered_server_id] = time.time()
                            
                            # Add to unified group view
                            group_view = get_group_view()
                            group_view.add_participant(str(discovered_server_id), 'server', (server_ip, 0), server_name)
                            
                            safe_print(f"Discovered server: {server_name} at {server_ip} (ID: {discovered_server_id})")
                            
                            # Only trigger election if we have fault tolerance enabled and partition detection is ready
                            ft_manager = get_fault_tolerance_manager()
                            if ft_manager and ft_manager.partition_detector.partition_detection_enabled:
                                # Trigger election when new server joins, but only after startup grace period
                                if len(group_view_servers) > 1:
                                    trigger_election()
                            else:
                                safe_print("Delaying election trigger until fault tolerance is ready")
                        else:
                            safe_print(f"Ignoring own announcement from {server_name} (ID: {discovered_server_id})")
                    continue  # Don't send response for server announcements
                
                # Handle server probes
                elif msg.startswith("SERVER_PROBE:"):
                    parts = msg.split(":")
                    if len(parts) >= 3:
                        probe_server_id = parts[2]
                        if probe_server_id != str(server_id):
                            response = f"SERVER_RESPONSE:{hostname}:{server_ip}"
                            safe_print(f"Responding to server probe from {parts[1]} (Server ID: {probe_server_id})")
                        else:
                            safe_print(f"Ignoring probe from self: {probe_server_id}")
                            continue
                    elif len(parts) >= 2:
                        # Legacy probe format
                        response = f"SERVER_RESPONSE:{hostname}:{server_ip}"
                        safe_print(f"Responding to legacy server probe from {parts[1]}")
                    else:
                        continue
                
                # Handle client heartbeats
                elif msg.startswith("CLIENT_HEARTBEAT:"):
                    parts = msg.split(":")
                    if len(parts) >= 2:
                        client_id = parts[1]
                        # Update client activity
                        client_last_seen[client_addr] = time.time()
                        group_view = get_group_view()
                        group_view.update_participant_activity(client_id)
                        safe_print(f"Received heartbeat from client {client_id}")
                    continue  # Don't send response for heartbeat messages
                
                # Handle system status requests
                elif msg == "status":
                    print_system_status()
                    group_view = get_group_view()
                    status = group_view.get_system_status()
                    response = f"\nSystem Status - Servers: {status['participant_counts']['active_servers']}, Clients: {status['participant_counts']['active_clients']}"
                
                # Handle election messages
                else:
                    try:
                        election_msg = json.loads(msg)
                        if election_msg.get("type") in ["ELECTION", "OK", "COORDINATOR"]:
                            handle_election_message(election_msg)
                            continue  # Don't send response for election messages
                    except json.JSONDecodeError:
                        pass
                    
                    response = f"\nYour message was received by {hostname}!"
                
                # Send response if one was generated
                if response:
                    UDP_socket.sendto(response.encode(), client_addr)
                    
            except Exception as e:
                safe_print(f"Error in multicast receiver: {e}")
                continue
                
    except Exception as e:
        safe_print(f"Failed to initialize multicast receiver: {e}")
    finally:
        if 'UDP_socket' in locals():
            UDP_socket.close()

def showSystemcomponents():
    safe_print(f'Servers in System: {group_view_servers}')
    safe_print(f'Leading Server: {get_current_leader()}')
    safe_print(f'Clients in System: {group_view_clients}')
    
    # Also show unified group view
    safe_print("\n" + "="*30)
    safe_print("UNIFIED GROUP VIEW:")
    print_system_status()
    

if __name__ == '__main__':
    # Initialize unified group view
    start_group_view()
    group_view = get_group_view()
    
    # Initialize fault tolerance system
    ft_manager = initialize_fault_tolerance(str(server_id), "server")
    
    # Add fault tolerance recovery callbacks
    def on_crash_recovery(failed_node_id):
        safe_print(f"Server crash detected: {failed_node_id}")
        if str(failed_node_id) == str(get_current_leader()):
            safe_print("Leader crashed, triggering election")
            trigger_election()
        # Remove from group views
        if int(failed_node_id) in group_view_servers:
            group_view_servers.discard(int(failed_node_id))
        group_view.remove_participant(str(failed_node_id))
    
    def on_partition_recovery(partition_detector):
        total_known_nodes = len(partition_detector.known_nodes)
        reachable_nodes = len(partition_detector.reachable_nodes)
        
        # Only process partition events if we have multiple nodes in the system and partition detection is enabled
        if total_known_nodes > 1 and partition_detector.partition_detection_enabled:
            if partition_detector.in_partition:
                safe_print(f"⚠️  Network partition detected! Reachable: {reachable_nodes}/{total_known_nodes}")
                safe_print("   Entering partition mode - pausing leader election until healed")
            else:
                safe_print(f"✅ Network partition healed! Reachable: {reachable_nodes}/{total_known_nodes}")
                safe_print("   Resuming normal operation and triggering leader election")
                trigger_election()
        elif not partition_detector.partition_detection_enabled:
            safe_print(f"Partition detection disabled - ignoring partition status during startup grace period")
    
    ft_manager.register_recovery_callback('crash', on_crash_recovery)
    ft_manager.register_recovery_callback('partition', on_partition_recovery)
    
    # Initialize election system
    initialize_election(server_id, server_ip)
    
    # Initialize enhanced discovery manager
    discovery_manager = DiscoveryManager(str(server_id), server_ip, socket.gethostname())
    
    # Add discovery callbacks
    def on_startup_complete():
        safe_print("Discovery startup phase completed")
    
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
    
    # Start fault tolerance first
    ft_manager.start()
    
    # Start integrated multicast receiver early so we can receive messages
    receiver_thread = threading.Thread(target=multicast_receiver, daemon=True)
    receiver_thread.start()
    
    # Wait a moment for receiver to initialize
    time.sleep(1)
    
    # Start enhanced discovery (this will handle timing and elections)
    discovery_manager.start_discovery()
    
    safe_print("Server startup complete with fault tolerance enabled")
    safe_print("Discovery statistics:")
    stats = discovery_manager.get_discovery_statistics()
    for key, value in stats.items():
        safe_print(f"  {key}: {value}")
    
    safe_print("\nFault tolerance statistics:")
    ft_stats = ft_manager.get_fault_statistics()
    for key, value in ft_stats.items():
        safe_print(f"  {key}: {value}")
    
    # Wait a bit for initial discovery, then show system status
    time.sleep(5)
    showSystemcomponents()
    
    # Start periodic system status display
    def periodic_status_display():
        while True:
            time.sleep(10)  # Display every 10 seconds
            safe_print("\n" + "="*50)
            safe_print("PERIODIC SYSTEM STATUS UPDATE")
            safe_print("="*50)
            showSystemcomponents()
    
    status_thread = threading.Thread(target=periodic_status_display, daemon=True)
    status_thread.start()
    
    # Keep main thread alive to allow daemon threads to continue
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        safe_print("\nServer shutting down...")
        sys.exit(0)