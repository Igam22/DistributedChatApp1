import socket
import threading
import time
import json
from resources.utils import group_view_servers, current_leader, leader_election_in_progress, my_server_id, MULTICAST_GROUP_ADDRESS

class BullyLeaderElection:
    def __init__(self, server_id, server_ip):
        self.server_id = server_id
        self.server_ip = server_ip
        self.election_timeout = 5  # seconds
        self.coordinator_timeout = 10  # seconds
        self.ok_received = False
        self.election_responses = set()
        
    def get_higher_priority_servers(self):
        """Get servers with higher priority (higher IDs)"""
        return [server for server in group_view_servers if server > self.server_id]
    
    def get_lower_priority_servers(self):
        """Get servers with lower priority (lower IDs)"""
        return [server for server in group_view_servers if server < self.server_id]
    
    def send_election_message(self, target_servers):
        """Send ELECTION message to higher priority servers"""
        if not target_servers:
            return
            
        election_msg = {
            "type": "ELECTION",
            "sender_id": self.server_id,
            "sender_ip": self.server_ip
        }
        
        for server in target_servers:
            self.send_message(server, election_msg)
    
    def send_ok_message(self, target_server):
        """Send OK message to the requesting server"""
        ok_msg = {
            "type": "OK",
            "sender_id": self.server_id,
            "sender_ip": self.server_ip
        }
        self.send_message(target_server, ok_msg)
    
    def send_coordinator_message(self):
        """Send COORDINATOR message to all other servers"""
        coordinator_msg = {
            "type": "COORDINATOR",
            "sender_id": self.server_id,
            "sender_ip": self.server_ip
        }
        
        for server in group_view_servers:
            if server != self.server_id:
                self.send_message(server, coordinator_msg)
    
    def send_message(self, target_server, message):
        """Send message to target server via multicast"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            
            # Add target server info to message
            message["target_server"] = target_server
            msg_str = json.dumps(message)
            sock.sendto(msg_str.encode(), MULTICAST_GROUP_ADDRESS)
            sock.close()
        except Exception as e:
            print(f"Error sending message to {target_server}: {e}")
    
    def start_election(self):
        """Start the bully election process"""
        global leader_election_in_progress, current_leader
        
        if leader_election_in_progress:
            return  # Election already in progress
            
        leader_election_in_progress = True
        print(f"Server {self.server_id} starting election")
        
        higher_priority_servers = self.get_higher_priority_servers()
        
        if not higher_priority_servers:
            # No higher priority servers, declare self as leader
            self.become_leader()
            return
        
        # Send ELECTION message to higher priority servers
        self.ok_received = False
        self.send_election_message(higher_priority_servers)
        
        # Wait for OK responses
        time.sleep(self.election_timeout)
        
        if not self.ok_received:
            # No OK received, become leader
            self.become_leader()
        else:
            # OK received, wait for coordinator message
            time.sleep(self.coordinator_timeout)
            if current_leader is None:
                # No coordinator message received, restart election
                leader_election_in_progress = False
                self.start_election()
    
    def become_leader(self):
        """Become the leader and notify other servers"""
        global current_leader, leader_election_in_progress
        
        current_leader = self.server_id
        leader_election_in_progress = False
        
        print(f"Server {self.server_id} is now the leader")
        self.send_coordinator_message()
    
    def handle_election_message(self, sender_id, sender_ip):
        """Handle incoming ELECTION message"""
        if sender_id < self.server_id:
            # Send OK response
            self.send_ok_message(sender_id)
            
            # Start own election if not already in progress
            if not leader_election_in_progress:
                threading.Thread(target=self.start_election, daemon=True).start()
    
    def handle_ok_message(self, sender_id):
        """Handle incoming OK message"""
        self.ok_received = True
        self.election_responses.add(sender_id)
    
    def handle_coordinator_message(self, sender_id):
        """Handle incoming COORDINATOR message"""
        global current_leader, leader_election_in_progress
        
        current_leader = sender_id
        leader_election_in_progress = False
        print(f"Server {sender_id} is now the leader")
    
    def process_election_message(self, message):
        """Process incoming election-related messages"""
        msg_type = message.get("type")
        sender_id = message.get("sender_id")
        sender_ip = message.get("sender_ip")
        target_server = message.get("target_server")
        
        # Only process messages meant for this server
        if target_server and target_server != self.server_id:
            return
        
        if msg_type == "ELECTION":
            self.handle_election_message(sender_id, sender_ip)
        elif msg_type == "OK":
            self.handle_ok_message(sender_id)
        elif msg_type == "COORDINATOR":
            self.handle_coordinator_message(sender_id)

# Global election instance
election_instance = None

def initialize_election(server_id, server_ip):
    """Initialize the election system"""
    global election_instance, my_server_id
    my_server_id = server_id
    election_instance = BullyLeaderElection(server_id, server_ip)

def trigger_election():
    """Trigger a new election"""
    if election_instance:
        threading.Thread(target=election_instance.start_election, daemon=True).start()

def handle_election_message(message):
    """Handle incoming election message"""
    if election_instance:
        election_instance.process_election_message(message)

def is_leader():
    """Check if this server is the current leader"""
    return current_leader == my_server_id

def get_current_leader():
    """Get the current leader ID"""
    return current_leader

def detect_leader_failure():
    """Detect if the current leader has failed"""
    global current_leader
    if current_leader and current_leader not in group_view_servers:
        print(f"Leader {current_leader} has failed, triggering election")
        current_leader = None
        trigger_election()