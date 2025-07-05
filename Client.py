#!/usr/bin/env python3
"""
Simple Chat Client
- UDP multicast communication
- Basic chat functionality

Version: 0.3.0
"""

import socket
import threading
import time

# Version
VERSION = "0.3.0"

# Configuration
MULTICAST_IP = '224.1.1.1'
MULTICAST_PORT = 5008
MULTICAST_GROUP = (MULTICAST_IP, MULTICAST_PORT)
BUFFER_SIZE = 1024

class ChatClient:
    def __init__(self, username=None, group=None):
        self.username = username or f"User_{int(time.time()) % 10000}"
        self.group = group or "general"
        self.socket = None
        self.listener_socket = None
        self.running = False
        
        # Heartbeat configuration
        self.heartbeat_interval = 7.0  # Send heartbeat every 7 seconds
        self.server_timeout = 20.0     # Consider server dead after 20 seconds
        self.last_server_response = time.time()
        self.connected_to_server = False
        
        print(f"Chat Client starting...")
        print(f"Version: {VERSION}")
        print(f"Username: {self.username}")
        print(f"Group: {self.group}")
    
    def setup_socket(self):
        """Setup UDP sockets"""
        try:
            # Main socket for sending
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            self.socket.settimeout(5)
            
            # Listener socket for receiving messages
            self.listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listener_socket.bind(('', MULTICAST_PORT))
            
            # Join multicast group for listening
            import struct
            mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_IP), socket.INADDR_ANY)
            self.listener_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.listener_socket.settimeout(1)  # Short timeout for responsive shutdown
            
            print(f"✅ Sockets setup successfully")
            return True
            
        except Exception as e:
            print(f"❌ Socket setup failed: {e}")
            return False
    
    def join_chat(self):
        """Send join request to servers"""
        try:
            join_message = f"join:{self.username}:{self.group}"
            self.socket.sendto(join_message.encode(), MULTICAST_GROUP)
            
            # Wait for response
            try:
                response, server_addr = self.socket.recvfrom(BUFFER_SIZE)
                print(f"✅ {response.decode()}")
                self.last_server_response = time.time()
                self.connected_to_server = True
                return True
            except socket.timeout:
                print("⚠️  No response from servers - but continuing anyway")
                return True
                
        except Exception as e:
            print(f"❌ Join failed: {e}")
            return False
    
    def send_message(self, message):
        """Send a chat message"""
        try:
            formatted_message = f"group_msg:{self.group}:{self.username}:{message}"
            self.socket.sendto(formatted_message.encode(), MULTICAST_GROUP)
            
            # Wait for acknowledgment
            try:
                response, server_addr = self.socket.recvfrom(BUFFER_SIZE)
                print(f"✅ {response.decode()}")
                self.last_server_response = time.time()
                self.connected_to_server = True
            except socket.timeout:
                print("⚠️  No response from server")
                
        except Exception as e:
            print(f"❌ Send failed: {e}")
    
    def request_status(self):
        """Request system status"""
        try:
            self.socket.sendto("status".encode(), MULTICAST_GROUP)
            
            try:
                response, server_addr = self.socket.recvfrom(BUFFER_SIZE)
                print(f"📊 {response.decode()}")
                self.last_server_response = time.time()
                self.connected_to_server = True
            except socket.timeout:
                print("⚠️  No status response")
                
        except Exception as e:
            print(f"❌ Status request failed: {e}")
    
    def send_heartbeat(self):
        """Send heartbeat to server"""
        try:
            heartbeat_message = f"client_heartbeat:{self.username}:{self.group}"
            self.socket.sendto(heartbeat_message.encode(), MULTICAST_GROUP)
            
            # Don't wait for response to avoid blocking - heartbeat should be fire-and-forget
            # Server response tracking happens in other methods
            
        except Exception as e:
            print(f"❌ Heartbeat send failed: {e}")
    
    def heartbeat_monitor(self):
        """Monitor server connection and send heartbeats"""
        while self.running:
            try:
                # Send heartbeat
                self.send_heartbeat()
                
                # Check if server is still responding
                if self.connected_to_server:
                    time_since_response = time.time() - self.last_server_response
                    if time_since_response > self.server_timeout:
                        print(f"💀 Server appears dead (no response for {time_since_response:.1f}s)")
                        self.connected_to_server = False
                        self.attempt_reconnection()
                
                time.sleep(self.heartbeat_interval)
                
            except Exception as e:
                if self.running:
                    print(f"❌ Heartbeat monitor error: {e}")
                    
    def attempt_reconnection(self):
        """Attempt to reconnect to server"""
        print("🔄 Attempting to reconnect to server...")
        
        # Try to rejoin the chat
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"🔄 Reconnection attempt {attempt + 1}/{max_retries}")
                
                # Send join message again
                join_message = f"join:{self.username}:{self.group}"
                self.socket.sendto(join_message.encode(), MULTICAST_GROUP)
                
                # Wait for response with shorter timeout
                try:
                    self.socket.settimeout(3)  # Shorter timeout for reconnection
                    response, server_addr = self.socket.recvfrom(BUFFER_SIZE)
                    print(f"✅ Reconnected! {response.decode()}")
                    self.last_server_response = time.time()
                    self.connected_to_server = True
                    self.socket.settimeout(5)  # Restore original timeout
                    return True
                except socket.timeout:
                    print(f"⚠️  No response on attempt {attempt + 1}")
                    continue
                    
            except Exception as e:
                print(f"❌ Reconnection attempt {attempt + 1} failed: {e}")
                
            time.sleep(2)  # Wait before next attempt
            
        print("💀 All reconnection attempts failed")
        self.socket.settimeout(5)  # Restore original timeout
        return False
    
    def message_listener(self):
        """Thread function to listen for incoming messages"""
        try:
            while self.running:
                try:
                    data, sender_addr = self.listener_socket.recvfrom(BUFFER_SIZE)
                    message = data.decode().strip()
                    
                    # Only show messages that start with our group prefix
                    if message.startswith(f"[{self.group}]"):
                        # Extract the username from the message to avoid showing our own messages
                        try:
                            # Format: [group] username: content
                            parts = message.split("] ", 1)
                            if len(parts) > 1:
                                username_and_content = parts[1]
                                username = username_and_content.split(":", 1)[0].strip()
                                
                                # Don't show our own messages
                                if username != self.username:
                                    print(f"\n{message}")
                                    print(f"{self.username}> ", end="", flush=True)
                        except:
                            # If parsing fails, show the message anyway
                            print(f"\n{message}")
                            print(f"{self.username}> ", end="", flush=True)
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"⚠️  Listener error: {e}")
                    break
        except Exception as e:
            print(f"⚠️  Message listener failed: {e}")
    
    def start(self):
        """Start the client"""
        if not self.setup_socket():
            return False
        
        if not self.join_chat():
            return False
        
        self.running = True
        
        # Start message listener thread
        listener_thread = threading.Thread(target=self.message_listener, daemon=True)
        listener_thread.start()
        
        # Start heartbeat monitor thread
        heartbeat_thread = threading.Thread(target=self.heartbeat_monitor, daemon=True)
        heartbeat_thread.start()
        print(f"💓 Heartbeat monitor started (interval: {self.heartbeat_interval}s)")
        
        print(f"\n🚀 Connected to chat! Commands:")
        print(f"  - Type messages to chat")
        print(f"  - '/status' for system status")
        print(f"  - '/quit' to exit")
        print("-" * 40)
        
        try:
            while self.running:
                user_input = input(f"{self.username}> ").strip()
                
                if user_input.lower() in ['/quit', 'quit', 'exit']:
                    break
                elif user_input.lower() == '/status':
                    self.request_status()
                elif user_input:
                    self.send_message(user_input)
                    
        except KeyboardInterrupt:
            print("\n🛑 Disconnecting...")
        finally:
            self.stop()
    
    def leave_chat(self):
        """Send leave notification to servers"""
        try:
            leave_message = f"leave:{self.username}:{self.group}"
            self.socket.sendto(leave_message.encode(), MULTICAST_GROUP)
        except Exception as e:
            print(f"⚠️  Leave notification failed: {e}")
    
    def stop(self):
        """Stop the client"""
        self.running = False
        if self.socket:
            self.leave_chat()
            self.socket.close()
        if self.listener_socket:
            self.listener_socket.close()
        print("✅ Client disconnected")

def main():
    import sys
    username = sys.argv[1] if len(sys.argv) > 1 else None
    group = sys.argv[2] if len(sys.argv) > 2 else None
    
    client = ChatClient(username, group)
    client.start()

if __name__ == "__main__":
    main()