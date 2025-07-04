import socket
import threading
import time
import json
from typing import Set, Dict, Optional, Callable
from resources.utils import MULTICAST_GROUP_ADDRESS, group_view_servers, server_last_seen, generate_server_id
from LeaderElection import trigger_election

class DiscoveryPhase:
    """Represents different phases of discovery"""
    STARTUP = "startup"
    RUNNING = "running"
    JOINING = "joining"

class DiscoveryManager:
    """Enhanced discovery manager with proper timing and retry mechanisms"""
    
    def __init__(self, server_id: str, server_ip: str, hostname: str):
        self.server_id = server_id
        self.server_ip = server_ip
        self.hostname = hostname
        
        # Discovery configuration
        self.startup_discovery_timeout = 15  # seconds
        self.probe_timeout = 5  # seconds
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        
        # Discovery state
        self.discovery_phase = DiscoveryPhase.STARTUP
        self.discovery_complete = False
        self.discovered_servers: Set[str] = set()
        self.discovery_callbacks: Dict[str, Callable] = {}
        
        # Threading
        self.discovery_thread = None
        self.announcement_thread = None
        self.running = False
        
        # Statistics
        self.discovery_attempts = 0
        self.successful_discoveries = 0
        self.failed_discoveries = 0
    
    def start_discovery(self):
        """Start the discovery process"""
        if self.running:
            return
            
        self.running = True
        print(f"Starting discovery for server {self.server_id}")
        
        # Start announcement thread immediately
        self.announcement_thread = threading.Thread(target=self._announcement_loop, daemon=True)
        self.announcement_thread.start()
        
        # Start discovery thread
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()
    
    def stop_discovery(self):
        """Stop the discovery process"""
        self.running = False
        if self.discovery_thread:
            self.discovery_thread.join()
        if self.announcement_thread:
            self.announcement_thread.join()
    
    def add_discovery_callback(self, event_type: str, callback: Callable):
        """Add callback for discovery events"""
        self.discovery_callbacks[event_type] = callback
    
    def _discovery_loop(self):
        """Main discovery loop with different phases"""
        while self.running:
            if self.discovery_phase == DiscoveryPhase.STARTUP:
                self._startup_discovery()
            elif self.discovery_phase == DiscoveryPhase.RUNNING:
                self._maintenance_discovery()
            elif self.discovery_phase == DiscoveryPhase.JOINING:
                self._joining_discovery()
            
            time.sleep(10)  # Check every 10 seconds
    
    def _startup_discovery(self):
        """Comprehensive startup discovery with retries"""
        print(f"Server {self.server_id}: Starting startup discovery phase")
        
        # Perform multiple discovery rounds
        for attempt in range(self.max_retries):
            self.discovery_attempts += 1
            print(f"Discovery attempt {attempt + 1}/{self.max_retries}")
            
            discovered_count = self._perform_discovery_round()
            
            if discovered_count > 0:
                self.successful_discoveries += 1
                print(f"Discovered {discovered_count} servers in attempt {attempt + 1}")
            else:
                self.failed_discoveries += 1
                print(f"No servers discovered in attempt {attempt + 1}")
            
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)
        
        # Wait additional time for late responses
        print(f"Waiting {self.startup_discovery_timeout - (self.max_retries * self.retry_delay)} seconds for additional responses...")
        time.sleep(max(0, self.startup_discovery_timeout - (self.max_retries * self.retry_delay)))
        
        # Discovery complete
        self.discovery_complete = True
        self.discovery_phase = DiscoveryPhase.RUNNING
        
        print(f"Startup discovery complete. Found {len(self.discovered_servers)} servers: {self.discovered_servers}")
        
        # Trigger election after discovery is complete
        self._trigger_callback('startup_complete')
        
        # Wait a bit more before triggering election to ensure all servers are ready
        time.sleep(3)
        print(f"Triggering election after startup discovery")
        trigger_election()
    
    def _maintenance_discovery(self):
        """Ongoing discovery for maintenance"""
        # Perform lightweight discovery every 30 seconds
        if time.time() % 30 < 10:  # Every 30 seconds
            self._perform_discovery_round()
    
    def _joining_discovery(self):
        """Discovery when joining an existing system"""
        print(f"Server {self.server_id}: Performing joining discovery")
        
        for attempt in range(self.max_retries):
            discovered_count = self._perform_discovery_round()
            
            if discovered_count > 0:
                break
            
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)
        
        # Switch to running mode
        self.discovery_phase = DiscoveryPhase.RUNNING
        self._trigger_callback('joining_complete')
    
    def _perform_discovery_round(self) -> int:
        """Perform one round of server discovery"""
        initial_count = len(self.discovered_servers)
        
        try:
            # Send probe message
            probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe_socket.settimeout(self.probe_timeout)
            
            probe_msg = f"SERVER_PROBE:{self.server_ip}:{self.server_id}"
            probe_socket.sendto(probe_msg.encode(), MULTICAST_GROUP_ADDRESS)
            
            # Listen for responses
            start_time = time.time()
            while time.time() - start_time < self.probe_timeout:
                try:
                    data, addr = probe_socket.recvfrom(1024)
                    response = data.decode()
                    
                    if response.startswith("SERVER_RESPONSE:"):
                        self._process_server_response(response, addr)
                    elif response.startswith("SERVER_ALIVE:"):
                        self._process_server_alive(response)
                        
                except socket.timeout:
                    break
                except Exception as e:
                    print(f"Error receiving discovery response: {e}")
                    break
            
            probe_socket.close()
            
        except Exception as e:
            print(f"Error in discovery round: {e}")
            return 0
        
        return len(self.discovered_servers) - initial_count
    
    def _process_server_response(self, response: str, addr):
        """Process SERVER_RESPONSE message"""
        try:
            parts = response.split(":")
            if len(parts) >= 3:
                response_type, hostname, server_ip = parts[0], parts[1], parts[2]
                server_id = generate_server_id(server_ip, hostname)
                
                if str(server_id) != str(self.server_id):  # Don't discover self
                    self.discovered_servers.add(str(server_id))
                    
                    # Add to global views
                    group_view_servers.add(server_id)
                    server_last_seen[server_id] = time.time()
                    
                    print(f"Discovered server via response: {hostname} (ID: {server_id})")
                    self._trigger_callback('server_discovered', server_id)
                    
        except Exception as e:
            print(f"Error processing server response: {e}")
    
    def _process_server_alive(self, message: str):
        """Process SERVER_ALIVE message"""
        try:
            parts = message.split(":")
            if len(parts) >= 3:
                msg_type, server_ip, hostname = parts[0], parts[1], parts[2]
                server_id = generate_server_id(server_ip, hostname)
                
                if str(server_id) != str(self.server_id):  # Don't discover self
                    self.discovered_servers.add(str(server_id))
                    
                    # Add to global views
                    group_view_servers.add(server_id)
                    server_last_seen[server_id] = time.time()
                    
                    print(f"Discovered server via alive: {hostname} (ID: {server_id})")
                    self._trigger_callback('server_discovered', server_id)
                    
        except Exception as e:
            print(f"Error processing server alive: {e}")
    
    def _announcement_loop(self):
        """Continuous server announcement loop"""
        announce_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        announce_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        
        while self.running:
            try:
                # Enhanced announcement with discovery phase info
                server_info = f"SERVER_ALIVE:{self.server_ip}:{self.hostname}:{self.discovery_phase}"
                announce_socket.sendto(server_info.encode(), MULTICAST_GROUP_ADDRESS)
                
                # Also send discovery probe response capability
                probe_response = f"SERVER_PROBE_CAPABLE:{self.server_ip}:{self.hostname}:{self.server_id}"
                announce_socket.sendto(probe_response.encode(), MULTICAST_GROUP_ADDRESS)
                
                time.sleep(10)  # Announce every 10 seconds
                
            except Exception as e:
                print(f"Error in announcement loop: {e}")
                time.sleep(10)
        
        announce_socket.close()
    
    def _trigger_callback(self, event_type: str, *args):
        """Trigger discovery callback"""
        if event_type in self.discovery_callbacks:
            try:
                self.discovery_callbacks[event_type](*args)
            except Exception as e:
                print(f"Error in discovery callback {event_type}: {e}")
    
    def get_discovery_statistics(self) -> Dict:
        """Get discovery statistics"""
        return {
            'discovery_phase': self.discovery_phase,
            'discovery_complete': self.discovery_complete,
            'discovered_servers_count': len(self.discovered_servers),
            'discovered_servers': list(self.discovered_servers),
            'discovery_attempts': self.discovery_attempts,
            'successful_discoveries': self.successful_discoveries,
            'failed_discoveries': self.failed_discoveries
        }
    
    def force_discovery_phase(self, phase: str):
        """Force discovery to a specific phase (for testing)"""
        self.discovery_phase = phase
        print(f"Discovery phase forced to: {phase}")
    
    def trigger_joining_discovery(self):
        """Trigger discovery when joining an existing system"""
        if self.discovery_phase == DiscoveryPhase.RUNNING:
            self.discovery_phase = DiscoveryPhase.JOINING
            print("Triggered joining discovery phase")

# Enhanced client discovery with retry mechanism
class ClientDiscovery:
    """Client discovery with retry and timeout mechanisms"""
    
    def __init__(self, client_id: str, max_retries: int = 3, timeout: int = 5):
        self.client_id = client_id
        self.max_retries = max_retries
        self.timeout = timeout
        self.discovery_attempts = 0
        
    def discover_servers(self) -> Optional[str]:
        """Discover servers with retry mechanism"""
        for attempt in range(self.max_retries):
            self.discovery_attempts += 1
            print(f"Client {self.client_id}: Discovery attempt {attempt + 1}/{self.max_retries}")
            
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(self.timeout)
                
                # Send join message
                join_msg = f"join:{self.client_id}"
                sock.sendto(join_msg.encode(), MULTICAST_GROUP_ADDRESS)
                
                # Wait for response
                response, server_addr = sock.recvfrom(1024)
                sock.close()
                
                print(f"Client {self.client_id}: Connected to server at {server_addr}")
                return response.decode()
                
            except socket.timeout:
                print(f"Client {self.client_id}: Discovery attempt {attempt + 1} timed out")
                if attempt < self.max_retries - 1:
                    time.sleep(2)  # Wait before retry
                    
            except Exception as e:
                print(f"Client {self.client_id}: Discovery attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)  # Wait before retry
        
        print(f"Client {self.client_id}: Failed to discover servers after {self.max_retries} attempts")
        return None