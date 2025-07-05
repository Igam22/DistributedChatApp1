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
    def __init__(self, username=None):
        self.username = username or f"User_{int(time.time()) % 10000}"
        self.socket = None
        self.running = False
        
        print(f"Chat Client starting...")
        print(f"Username: {self.username}")
    
    def setup_socket(self):
        """Setup UDP socket"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            self.socket.settimeout(5)
            
            print(f"✅ Socket setup successfully")
            return True
            
        except Exception as e:
            print(f"❌ Socket setup failed: {e}")
            return False
    
    def join_chat(self):
        """Send join request to servers"""
        try:
            join_message = f"join:{self.username}"
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
            formatted_message = f"[{self.username}]: {message}"
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
    
    def start(self):
        """Start the client"""
        if not self.setup_socket():
            return False
        
        if not self.join_chat():
            return False
        
        self.running = True
        
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
    
    def stop(self):
        """Stop the client"""
        self.running = False
        if self.socket:
            self.socket.close()
        print("✅ Client disconnected")

def main():
    import sys
    username = sys.argv[1] if len(sys.argv) > 1 else None
    
    client = ChatClient(username)
    client.start()

if __name__ == "__main__":
    main()