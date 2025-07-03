import socket
import threading
import time
import uuid
from resources.utils import MULTICAST_GROUP_ADDRESS
from DiscoveryManager import ClientDiscovery
from FaultTolerance import initialize_fault_tolerance, get_fault_tolerance_manager

class ChatClient:
    """Enhanced chat client with heartbeat and group view support"""
    
    def __init__(self, username=None):
        self.username = username or f"User_{uuid.uuid4().hex[:8]}"
        self.client_id = f"{self.username}_{uuid.uuid4().hex[:8]}"
        self.socket = None
        self.connected = False
        self.heartbeat_thread = None
        self.heartbeat_interval = 30  # seconds
        self.ft_manager = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
    def connect(self):
        """Connect to the distributed chat system with enhanced discovery"""
        try:
            # Use enhanced discovery manager
            client_discovery = ClientDiscovery(self.client_id, max_retries=3, timeout=5)
            response = client_discovery.discover_servers()
            
            if response is None:
                print("Failed to discover any servers")
                return False
            
            # Create socket for communication
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(10)
            
            print(f"Successfully connected to distributed chat system")
            print(f"Server response: {response}")
            
            self.connected = True
            self.reconnect_attempts = 0
            
            # Initialize fault tolerance for client
            self.ft_manager = initialize_fault_tolerance(self.client_id, "client")
            
            # Add reconnection recovery callback
            def on_connection_failure(failed_node_id):
                print(f"Connection failure detected, attempting reconnection...")
                self._attempt_reconnection()
            
            self.ft_manager.register_recovery_callback('crash', on_connection_failure)
            self.ft_manager.start()
            
            # Start heartbeat thread
            self.start_heartbeat()
            
            return True
            
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    def start_heartbeat(self):
        """Start sending periodic heartbeat messages"""
        if self.heartbeat_thread is None:
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self.heartbeat_thread.start()
    
    def _heartbeat_loop(self):
        """Send heartbeat messages periodically"""
        while self.connected:
            try:
                heartbeat_msg = f"CLIENT_HEARTBEAT:{self.client_id}"
                self.socket.sendto(heartbeat_msg.encode(), MULTICAST_GROUP_ADDRESS)
                time.sleep(self.heartbeat_interval)
            except Exception as e:
                print(f"Heartbeat failed: {e}")
                break
    
    def send_message(self, message):
        """Send a message to the chat system"""
        if not self.connected:
            print("Not connected to chat system")
            return False
        
        try:
            formatted_msg = f"[{self.username}]: {message}"
            self.socket.sendto(formatted_msg.encode(), MULTICAST_GROUP_ADDRESS)
            
            # Wait for response
            response, server_addr = self.socket.recvfrom(1024)
            print(f"Server response: {response.decode()}")
            return True
            
        except Exception as e:
            print(f"Failed to send message: {e}")
            return False
    
    def request_status(self):
        """Request system status from the server"""
        if not self.connected:
            print("Not connected to chat system")
            return
        
        try:
            status_msg = "status"
            self.socket.sendto(status_msg.encode(), MULTICAST_GROUP_ADDRESS)
            
            # Wait for response
            response, server_addr = self.socket.recvfrom(1024)
            print(f"System Status: {response.decode()}")
            
        except Exception as e:
            print(f"Failed to get status: {e}")
    
    def disconnect(self):
        """Disconnect from the chat system"""
        self.connected = False
        if self.ft_manager:
            self.ft_manager.stop()
        if self.socket:
            self.socket.close()
        print(f"Client {self.username} disconnected")
    
    def _attempt_reconnection(self):
        """Attempt to reconnect to the system"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            print(f"Max reconnection attempts ({self.max_reconnect_attempts}) reached")
            return False
        
        self.reconnect_attempts += 1
        print(f"Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}")
        
        # Disconnect current connection
        self.connected = False
        if self.socket:
            self.socket.close()
        
        # Wait before reconnecting
        time.sleep(2 ** self.reconnect_attempts)  # Exponential backoff
        
        # Attempt to reconnect
        if self.connect():
            print("Reconnection successful!")
            return True
        else:
            print(f"Reconnection attempt {self.reconnect_attempts} failed")
            return False
    
    def interactive_mode(self):
        """Start interactive chat mode"""
        if not self.connect():
            return
        
        print(f"\nWelcome to the distributed chat system, {self.username}!")
        print("Available commands:")
        print("  - Type any message to send it")
        print("  - '/status' to get system status")
        print("  - '/quit' to exit")
        print("-" * 50)
        
        try:
            while self.connected:
                user_input = input(f"{self.username}> ").strip()
                
                if user_input.lower() == '/quit':
                    break
                elif user_input.lower() == '/status':
                    self.request_status()
                elif user_input:
                    self.send_message(user_input)
                    
        except KeyboardInterrupt:
            print("\nInterrupted by user")
        finally:
            self.disconnect()

def main():
    """Main function to run the client"""
    import sys
    
    username = None
    if len(sys.argv) > 1:
        username = sys.argv[1]
    
    client = ChatClient(username)
    client.interactive_mode()

if __name__ == "__main__":
    main()