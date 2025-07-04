import socket
import struct
import time
import json

from resources.utils import MULTICAST_GROUP_ADDRESS
from resources.utils import MULTICAST_IP
from resources.utils import MULTICAST_PORT
from resources.utils import BUFFER_SIZE
from resources.utils import group_view_servers
from resources.utils import group_view_clients
from resources.utils import server_last_seen
from resources.utils import client_last_seen
from LeaderElection import handle_election_message, get_current_leader, trigger_election
from GroupView import get_group_view, start_group_view, print_system_status
from FaultTolerance import get_fault_tolerance_manager
from resources.utils import generate_server_id

# Creating a UDP socket instance 
UDP_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Allowing the reuse 
UDP_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# Binding the socket to the Multicast port
UDP_socket.bind(('', MULTICAST_PORT)) 

# Joining the Multicast Group
mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_IP), socket.INADDR_ANY)
UDP_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

print(f"\nListening for messages on: {MULTICAST_GROUP_ADDRESS}")

# Start the unified group view
start_group_view()
group_view = get_group_view()

while True:
    try:   
        data, client_addr = UDP_socket.recvfrom(BUFFER_SIZE)
        msg = data.decode()
        print(f"Received message from {client_addr}: {msg}")
        
        # Handle message with fault tolerance if available
        ft_manager = get_fault_tolerance_manager()
        if ft_manager:
            processed_msg = ft_manager.handle_message(msg, client_addr)
            if processed_msg:
                if processed_msg.get('type') == 'reliable_message':
                    # Handle reliable message
                    reliable_msg = processed_msg['message']
                    print(f"Processing reliable message: {reliable_msg.msg_type} from {reliable_msg.sender_id}")
                    # Continue with normal processing
                elif processed_msg.get('type') == 'heartbeat_ack':
                    # Send heartbeat acknowledgment
                    response = json.dumps(processed_msg)
                    UDP_socket.sendto(response.encode(), client_addr)
                    continue

        if msg == "join" or msg.startswith("join:"):
            # Handle both legacy "join" and enhanced "join:client_id" formats
            if msg.startswith("join:"):
                parts = msg.split(":")
                client_id = parts[1] if len(parts) > 1 else f"{client_addr[0]}:{client_addr[1]}"
            else:
                client_id = f"{client_addr[0]}:{client_addr[1]}"
                
            print(f"\nClient {client_id} at {client_addr} wants to join.")
            
            # Add client to legacy view for backward compatibility
            group_view_clients.add(client_addr)
            client_last_seen[client_addr] = time.time()
            
            # Add client to unified group view
            group_view.add_participant(client_id, 'client', client_addr)
            
            leader_id = get_current_leader()
            leader_name = socket.gethostname() if leader_id else "No leader elected"
            response = f"\nWelcome {client_id}! Current Leader: {leader_name} (ID: {leader_id})"
        elif msg.startswith("SERVER_ALIVE:"):
            # Handle server announcements
            parts = msg.split(":")
            if len(parts) >= 3:
                server_ip = parts[1]
                server_name = parts[2]
                server_id = generate_server_id(server_ip, server_name)  # Use standardized ID generation
                
                # Get our own server ID for comparison
                my_ip = socket.gethostbyname(socket.gethostname())
                my_hostname = socket.gethostname()
                my_server_id = generate_server_id(my_ip, my_hostname)
                
                # Don't process our own announcements
                if server_id != my_server_id:
                    # Add to legacy views for backward compatibility
                    group_view_servers.add(server_id)
                    server_last_seen[server_id] = time.time()
                    
                    # Add to unified group view
                    group_view.add_participant(str(server_id), 'server', (server_ip, 0), server_name)
                    
                    print(f"Discovered server: {server_name} at {server_ip} (ID: {server_id})")
                    
                    # Trigger election when new server joins
                    if len(group_view_servers) > 1:
                        trigger_election()
                else:
                    print(f"Ignoring own announcement from {server_name} (ID: {server_id})")
            continue  # Don't send response for server announcements
        elif msg.startswith("SERVER_PROBE:"):
            # Enhanced server probe handling
            parts = msg.split(":")
            if len(parts) >= 3:
                msg_type, probe_ip, probe_server_id = parts[0], parts[1], parts[2]
                
                # Don't respond to our own probes
                my_server_id = generate_server_id(socket.gethostbyname(socket.gethostname()), socket.gethostname())
                if probe_server_id != str(my_server_id):
                    response = f"SERVER_RESPONSE:{socket.gethostname()}:{socket.gethostbyname(socket.gethostname())}"
                    print(f"Responding to enhanced server probe from {probe_ip} (Server ID: {probe_server_id})")
                else:
                    print(f"Ignoring probe from self: {probe_server_id}")
                    continue
            elif len(parts) >= 2:
                # Legacy probe format
                probe_ip = parts[1]
                response = f"SERVER_RESPONSE:{socket.gethostname()}:{socket.gethostbyname(socket.gethostname())}"
                print(f"Responding to legacy server probe from {probe_ip}")
            else:
                continue
        elif msg.startswith("SERVER_PROBE_CAPABLE:"):
            # Handle server probe capability announcements
            parts = msg.split(":")
            if len(parts) >= 4:
                msg_type, server_ip, hostname, server_id = parts[0], parts[1], parts[2], parts[3]
                print(f"Server {hostname} (ID: {server_id}) announced probe capability")
                
                # Add to group views if not already present
                server_id_int = int(server_id) if server_id.isdigit() else generate_server_id(server_ip, hostname)
                group_view_servers.add(server_id_int)
                server_last_seen[server_id_int] = time.time()
                
                # Add to unified group view
                group_view.add_participant(str(server_id_int), 'server', (server_ip, 0), hostname)
            continue  # Don't send response for capability announcements
        elif msg.startswith("CLIENT_HEARTBEAT:"):
            # Handle client heartbeat messages
            parts = msg.split(":")
            if len(parts) >= 2:
                client_id = parts[1]
                # Update client activity in both legacy and unified views
                client_last_seen[client_addr] = time.time()
                group_view.update_participant_activity(client_id)
                print(f"Received heartbeat from client {client_id}")
            continue  # Don't send response for heartbeat messages
        elif msg == "status":
            # Handle system status requests
            print_system_status()
            status = group_view.get_system_status()
            response = f"\nSystem Status - Servers: {status['participant_counts']['active_servers']}, Clients: {status['participant_counts']['active_clients']}"
        else:
            # Try to parse as JSON election message
            try:
                election_msg = json.loads(msg)
                if election_msg.get("type") in ["ELECTION", "OK", "COORDINATOR"]:
                    handle_election_message(election_msg)
                    continue  # Don't send response for election messages
            except json.JSONDecodeError:
                pass
            
            response = f"\nYour message was received by {socket.gethostname()}!"

        UDP_socket.sendto(response.encode(), client_addr)

    except KeyboardInterrupt:
        print("\nServer stopped by user.")
        UDP_socket.close()
        break

    except socket.timeout:
        print("\nTimeout: no response")
        UDP_socket.close()
        break
