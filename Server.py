import socket
import threading
import time
from resources.utils import group_view_servers
from resources.utils import group_view_clients
from resources.utils import server_last_seen
from resources.utils import MULTICAST_GROUP_ADDRESS

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

# Defining server attributes 
server_IP= getIP()
current_leader = None 






def announce_server():
    """Periodically announce this server's presence"""
    announce_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    announce_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    
    while True:
        server_info = f"SERVER_ALIVE:{server_IP}:{socket.gethostname()}"
        announce_socket.sendto(server_info.encode(), MULTICAST_GROUP_ADDRESS)
        time.sleep(10)  # Announce every 10 seconds

def probe_servers():
    """Actively probe for other servers"""
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe_socket.settimeout(2)
    
    probe_msg = f"SERVER_PROBE:{server_IP}"
    probe_socket.sendto(probe_msg.encode(), MULTICAST_GROUP_ADDRESS)
    
    # Listen for responses
    try:
        while True:
            data, addr = probe_socket.recvfrom(1024)
            if data.decode().startswith("SERVER_RESPONSE:"):
                group_view_servers.add(addr)
                server_last_seen[addr] = time.time()
    except socket.timeout:
        pass
    finally:
        probe_socket.close()

def cleanup_dead_servers():
    """Remove servers that haven't been seen recently"""
    current_time = time.time()
    dead_servers = []
    
    for server in list(group_view_servers):
        if current_time - server_last_seen.get(server, 0) > 30:  # 30 second timeout
            dead_servers.append(server)
    
    for server in dead_servers:
        group_view_servers.discard(server)
        server_last_seen.pop(server, None)
        print(f"Removed dead server: {server}")

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
    #print(f'Leading Server: {TODO!!!!!}')
    print(f'Clients in System: {group_view_clients}')
    

if __name__ == '__main__':
    start_server_discovery()
    probe_servers()
    showSystemcomponents()