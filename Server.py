#!/usr/bin/env python3
"""
Simple Distributed Chat Server
- UDP multicast communication
- Basic server discovery
- Clean, minimal implementation
"""

import socket
import threading
import time
import json
import hashlib

# Configuration
MULTICAST_IP = '224.1.1.1'
MULTICAST_PORT = 5008
MULTICAST_GROUP = (MULTICAST_IP, MULTICAST_PORT)
BUFFER_SIZE = 1024

# Global state
servers = {}  # {server_id: {'ip': ip, 'hostname': hostname, 'last_seen': timestamp}}
clients = set()  # Set of (ip, port) tuples

def get_local_ip():
    """Get local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

def generate_server_id(ip, hostname):
    """Generate unique server ID"""
    hash_input = f"{ip}:{hostname}"
    return int(hashlib.sha256(hash_input.encode()).hexdigest()[:8], 16) % 10000

class ChatServer:
    def __init__(self):
        self.ip = get_local_ip()
        self.hostname = socket.gethostname()
        self.server_id = generate_server_id(self.ip, self.hostname)
        self.running = True
        
        # Create sockets
        self.receiver_socket = None
        self.sender_socket = None
        
        print(f"Chat Server starting...")
        print(f"Server ID: {self.server_id}")
        print(f"IP: {self.ip}")
        print(f"Hostname: {self.hostname}")
    
    def setup_sockets(self):
        """Setup UDP multicast sockets"""
        try:
            # Receiver socket
            self.receiver_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.receiver_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.receiver_socket.bind(('', MULTICAST_PORT))
            
            # Join multicast group
            import struct
            mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_IP), socket.INADDR_ANY)
            self.receiver_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            
            # Sender socket
            self.sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sender_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            
            print(f"✅ Sockets setup successfully on {MULTICAST_GROUP}")
            return True
            
        except Exception as e:
            print(f"❌ Socket setup failed: {e}")
            return False
    
    def send_announcement(self):
        """Send server announcement"""
        try:
            message = f"SERVER_ALIVE:{self.ip}:{self.hostname}:{self.server_id}"
            self.sender_socket.sendto(message.encode(), MULTICAST_GROUP)
        except Exception as e:
            print(f"Error sending announcement: {e}")
    
    def handle_message(self, message, sender_addr):
        """Handle incoming messages"""
        try:
            if message.startswith("SERVER_ALIVE:"):
                # Parse server announcement
                parts = message.split(":")
                if len(parts) >= 4:
                    server_ip = parts[1]
                    server_hostname = parts[2]
                    server_id = int(parts[3])
                    
                    # Don't add ourselves
                    if server_id != self.server_id:
                        servers[server_id] = {
                            'ip': server_ip,
                            'hostname': server_hostname,
                            'last_seen': time.time()
                        }
                        print(f"📡 Discovered server: {server_hostname} (ID: {server_id}) at {server_ip}")
            
            elif message.startswith("join"):
                # Handle client join
                clients.add(sender_addr)
                print(f"👤 Client joined: {sender_addr}")
                response = f"Welcome! Server: {self.hostname} (ID: {self.server_id})"
                self.sender_socket.sendto(response.encode(), sender_addr)
            
            elif message == "status":
                # Handle status request
                status = {
                    'servers': len(servers) + 1,  # +1 for this server
                    'clients': len(clients),
                    'server_id': self.server_id
                }
                response = f"Status: {json.dumps(status)}"
                self.sender_socket.sendto(response.encode(), sender_addr)
            
            else:
                # Handle chat message
                if sender_addr in clients:
                    print(f"💬 Message from {sender_addr}: {message}")
                    response = f"Message received by {self.hostname}"
                    self.sender_socket.sendto(response.encode(), sender_addr)
                
        except Exception as e:
            print(f"Error handling message '{message}': {e}")
    
    def message_receiver(self):
        """Thread function to receive messages"""
        print("🔄 Message receiver started")
        
        while self.running:
            try:
                data, sender_addr = self.receiver_socket.recvfrom(BUFFER_SIZE)
                message = data.decode().strip()
                
                # Skip our own messages
                if sender_addr[0] == self.ip:
                    continue
                    
                print(f"📨 Received: '{message}' from {sender_addr}")
                self.handle_message(message, sender_addr)
                
            except Exception as e:
                if self.running:
                    print(f"Receiver error: {e}")
                break
    
    def announcer(self):
        """Thread function to send periodic announcements"""
        print("📢 Announcer started")
        
        while self.running:
            try:
                self.send_announcement()
                time.sleep(10)  # Announce every 10 seconds
            except Exception as e:
                if self.running:
                    print(f"Announcer error: {e}")
                break
    
    def cleanup_dead_servers(self):
        """Remove servers that haven't been seen recently"""
        current_time = time.time()
        dead_servers = []
        
        for server_id, info in servers.items():
            if current_time - info['last_seen'] > 30:  # 30 second timeout
                dead_servers.append(server_id)
        
        for server_id in dead_servers:
            server_info = servers.pop(server_id)
            print(f"🔴 Server timeout: {server_info['hostname']} (ID: {server_id})")
    
    def cleanup_thread(self):
        """Thread function for periodic cleanup"""
        while self.running:
            time.sleep(15)  # Cleanup every 15 seconds
            self.cleanup_dead_servers()
    
    def show_status(self):
        """Display current status"""
        print("\n" + "="*50)
        print("📊 SERVER STATUS")
        print("="*50)
        print(f"This Server: {self.hostname} (ID: {self.server_id}) at {self.ip}")
        print(f"Known Servers: {len(servers)}")
        for server_id, info in servers.items():
            print(f"  - {info['hostname']} (ID: {server_id}) at {info['ip']}")
        print(f"Connected Clients: {len(clients)}")
        for client in clients:
            print(f"  - {client}")
        print("="*50 + "\n")
    
    def status_thread(self):
        """Thread function to show periodic status"""
        while self.running:
            time.sleep(20)  # Show status every 20 seconds
            self.show_status()
    
    def start(self):
        """Start the server"""
        if not self.setup_sockets():
            return False
        
        # Add ourselves to the servers list
        servers[self.server_id] = {
            'ip': self.ip,
            'hostname': self.hostname,
            'last_seen': time.time()
        }
        
        # Start threads
        threads = [
            threading.Thread(target=self.message_receiver, daemon=True),
            threading.Thread(target=self.announcer, daemon=True),
            threading.Thread(target=self.cleanup_thread, daemon=True),
            threading.Thread(target=self.status_thread, daemon=True)
        ]
        
        for thread in threads:
            thread.start()
        
        print("🚀 Server started successfully!")
        self.show_status()
        
        try:
            # Keep main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Shutting down server...")
            self.stop()
    
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.receiver_socket:
            self.receiver_socket.close()
        if self.sender_socket:
            self.sender_socket.close()
        print("✅ Server stopped")

def main():
    server = ChatServer()
    server.start()

if __name__ == "__main__":
    main()