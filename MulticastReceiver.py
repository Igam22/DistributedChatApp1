import socket
import struct
import time

from resources.utils import MULTICAST_GROUP_ADDRESS
from resources.utils import MULTICAST_IP
from resources.utils import MULTICAST_PORT
from resources.utils import BUFFER_SIZE
from resources.utils import group_view_servers
from resources.utils import group_view_clients
from resources.utils import server_last_seen

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

while True:
    try:   
        data, client_addr = UDP_socket.recvfrom(BUFFER_SIZE)
        msg = data.decode()
        print(f"Received message from {client_addr}: {msg}")

        if msg == "join":
            print(f"\nClient {client_addr} wants to join.")
            
            for other_addr in group_view_clients:
                if other_addr != client_addr:
                    info_msg = f"Another node in the network: {other_addr}"
                    group_view_clients.add(client_addr)
                    

            response = f"\nI am the current Leader: {socket.gethostname()}"
        elif msg.startswith("SERVER_ALIVE:"):
            # Handle server announcements
            parts = msg.split(":")
            if len(parts) >= 3:
                server_ip = parts[1]
                server_name = parts[2]
                server_info = (server_ip, server_name)
                group_view_servers.add(server_info)
                server_last_seen[server_info] = time.time()
                print(f"Discovered server: {server_name} at {server_ip}")
            continue  # Don't send response for server announcements
        elif msg.startswith("SERVER_PROBE:"):
            # Respond to server probes
            parts = msg.split(":")
            if len(parts) >= 2:
                probe_ip = parts[1]
                response = f"SERVER_RESPONSE:{socket.gethostname()}:{socket.gethostbyname(socket.gethostname())}"
                print(f"Responding to server probe from {probe_ip}")
            else:
                continue
        else:
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
