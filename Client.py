#!/usr/bin/env python3
"""
Simple Chat Client
- UDP multicast communication
- Basic chat functionality
"""

import socket
import threading
import time

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
        
        print(f"Chat Client starting...")
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
            except socket.timeout:
                print("⚠️  No status response")
                
        except Exception as e:
            print(f"❌ Status request failed: {e}")
    
    def message_listener(self):
        """Thread function to listen for incoming messages"""
        try:
            while self.running:
                try:
                    data, sender_addr = self.listener_socket.recvfrom(BUFFER_SIZE)
                    message = data.decode().strip()
                    
                    # Only show messages that start with our group prefix
                    if message.startswith(f"[{self.group}]"):
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