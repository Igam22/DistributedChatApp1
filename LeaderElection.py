#!/usr/bin/env python3
"""
Leader Election using Bully Algorithm
- Implements the Bully Algorithm for leader election in distributed systems
- Handles election triggers: system start, new server joins, leader failure
- Uses node identification based on IP+Port+ProcessID for uniqueness
- Maintains Group View (membership view) of all active nodes

Version: 0.3.0

Node Identification:
- In distributed systems, nodes are commonly identified using a combination of:
  * IP Address: Network location
  * Port: Service endpoint
  * Process ID: Unique process identifier
- This creates a globally unique identifier that prevents conflicts

Group View:
- Group View (or Membership View) is a fundamental concept in distributed systems
- It represents the current set of active/alive nodes in the system
- All nodes maintain a consistent view of group membership
- Used for consensus, failure detection, and coordination
- Changes when nodes join, leave, or fail
"""

import socket
import threading
import time
import json
import os
from enum import Enum
from typing import Dict, Set, Optional, Tuple

# Version
VERSION = "0.3.0"

class NodeState(Enum):
    """Node states in the election process"""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"

class MessageType(Enum):
    """Election message types for Bully Algorithm"""
    ELECTION = "election"          # Start election
    ANSWER = "answer"              # Response to election
    COORDINATOR = "coordinator"    # Announce new leader
    HEARTBEAT = "heartbeat"        # Leader heartbeat
    HEARTBEAT_ACK = "heartbeat_ack" # Heartbeat acknowledgment

class NodeIdentifier:
    """
    Node Identification System
    
    In distributed systems, nodes need unique identifiers to prevent conflicts
    and enable proper coordination. Common approaches include:
    - IP + Port + ProcessID (used here)
    - UUID (Universally Unique Identifier)
    - Hostname + ProcessID
    - MAC Address + Timestamp
    
    We use IP + Port + ProcessID because:
    - IP: Identifies the machine/network location
    - Port: Identifies the specific service instance
    - ProcessID: Ensures uniqueness even with multiple processes on same machine
    """
    
    def __init__(self, ip: str, port: int, process_id: int):
        self.ip = ip
        self.port = port
        self.process_id = process_id
        # Create unique node ID by combining all components
        self.node_id = f"{ip}:{port}:{process_id}"
        
    def __str__(self):
        return self.node_id
        
    def __eq__(self, other):
        return isinstance(other, NodeIdentifier) and self.node_id == other.node_id
        
    def __hash__(self):
        return hash(self.node_id)
        
    def __lt__(self, other):
        """For ordering nodes - higher process_id has higher priority in Bully Algorithm"""
        if not isinstance(other, NodeIdentifier):
            return NotImplemented
        return self.process_id < other.process_id

class GroupView:
    """
    Group View Management
    
    Group View (Membership View) is a core concept in distributed systems:
    - Represents the current set of active nodes in the system
    - All nodes maintain a consistent view of group membership
    - Updated when nodes join, leave, or fail
    - Used for:
      * Failure detection
      * Consensus protocols
      * Load balancing
      * Coordination and synchronization
    
    Common implementations:
    - View-synchronous group communication
    - Gossip-based membership protocols
    - Centralized membership services
    """
    
    def __init__(self):
        self.members: Dict[NodeIdentifier, dict] = {}
        self.view_id = 0  # Incremented on each membership change
        self.lock = threading.Lock()
        
    def add_member(self, node_id: NodeIdentifier, info: dict):
        """Add a new member to the group view"""
        with self.lock:
            if node_id not in self.members:
                self.members[node_id] = info
                self.view_id += 1
                return True
            return False
            
    def remove_member(self, node_id: NodeIdentifier):
        """Remove a member from the group view"""
        with self.lock:
            if node_id in self.members:
                del self.members[node_id]
                self.view_id += 1
                return True
            return False
            
    def update_member(self, node_id: NodeIdentifier, info: dict):
        """Update member information"""
        with self.lock:
            if node_id in self.members:
                self.members[node_id].update(info)
                return True
            return False
            
    def get_members(self) -> Dict[NodeIdentifier, dict]:
        """Get current group members"""
        with self.lock:
            return self.members.copy()
            
    def get_view_id(self) -> int:
        """Get current view ID"""
        with self.lock:
            return self.view_id
            
    def get_higher_nodes(self, node_id: NodeIdentifier) -> Set[NodeIdentifier]:
        """Get nodes with higher priority (for Bully Algorithm)"""
        with self.lock:
            return {nid for nid in self.members.keys() if nid > node_id}
            
    def get_lower_nodes(self, node_id: NodeIdentifier) -> Set[NodeIdentifier]:
        """Get nodes with lower priority (for Bully Algorithm)"""
        with self.lock:
            return {nid for nid in self.members.keys() if nid < node_id}

class LeaderElection:
    """
    Bully Algorithm Implementation
    
    The Bully Algorithm is a classic leader election algorithm:
    1. When a node detects leader failure, it starts an election
    2. Node sends ELECTION message to all higher-priority nodes
    3. If no response from higher nodes, it becomes leader
    4. If higher nodes respond, they handle the election
    5. New leader sends COORDINATOR message to all nodes
    
    Election triggers:
    - System startup: All nodes start election to establish initial leader
    - New server joins: May trigger election if it has higher priority
    - Leader failure: Detected through heartbeat timeout
    """
    
    def __init__(self, node_id: NodeIdentifier, multicast_group: Tuple[str, int]):
        self.node_id = node_id
        self.multicast_group = multicast_group
        self.state = NodeState.FOLLOWER
        self.current_leader: Optional[NodeIdentifier] = None
        self.group_view = GroupView()
        
        # Election state
        self.election_in_progress = False
        self.election_timeout = 5.0  # seconds
        self.heartbeat_interval = 3.0  # seconds
        self.heartbeat_timeout = 10.0  # seconds
        self.last_heartbeat_time = time.time()
        
        # Networking
        self.socket = None
        self.receiver_socket = None
        self.running = False
        
        # Threading
        self.election_thread = None
        self.heartbeat_thread = None
        
    def setup_socket(self):
        """Setup UDP socket for election messages"""
        try:
            # Sender socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            self.socket.settimeout(1.0)
            
            # Receiver socket for listening to election messages
            self.receiver_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.receiver_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.receiver_socket.bind(('', self.multicast_group[1]))
            
            # Join multicast group
            import struct
            mreq = struct.pack("4sl", socket.inet_aton(self.multicast_group[0]), socket.INADDR_ANY)
            self.receiver_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.receiver_socket.settimeout(1.0)
            
            return True
        except Exception as e:
            print(f"❌ LeaderElection socket setup failed: {e}")
            return False
            
    def start(self):
        """Start the leader election system"""
        if not self.setup_socket():
            return False
            
        self.running = True
        
        # Add ourselves to group view
        self.group_view.add_member(self.node_id, {
            'state': self.state.value,
            'last_seen': time.time()
        })
        
        # Start background threads
        self.election_thread = threading.Thread(target=self._election_monitor, daemon=True)
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_monitor, daemon=True)
        
        self.election_thread.start()
        self.heartbeat_thread.start()
        
        print(f"🗳️  Leader Election started for node {self.node_id}")
        
        # Trigger initial election on system start
        self.trigger_election("system_start")
        
        return True
        
    def stop(self):
        """Stop the leader election system"""
        self.running = False
        if self.socket:
            self.socket.close()
        if self.receiver_socket:
            self.receiver_socket.close()
            
    def trigger_election(self, reason: str):
        """
        Trigger leader election
        
        Election triggers:
        - system_start: Initial election when system starts
        - new_server_joins: When a new server joins the group
        - leader_failure: When current leader fails/becomes unreachable
        """
        if self.election_in_progress:
            return
            
        print(f"🗳️  Triggering election due to: {reason}")
        threading.Thread(target=self._start_election, daemon=True).start()
        
    def _start_election(self):
        """Start the Bully Algorithm election process"""
        if self.election_in_progress:
            return
            
        self.election_in_progress = True
        self.state = NodeState.CANDIDATE
        
        print(f"🗳️  Node {self.node_id} starting election")
        
        # Get nodes with higher priority
        higher_nodes = self.group_view.get_higher_nodes(self.node_id)
        
        if not higher_nodes:
            # No higher priority nodes, we become leader
            self._become_leader()
        else:
            # Send election message to higher priority nodes
            responses = self._send_election_messages(higher_nodes)
            
            if not responses:
                # No responses from higher nodes, we become leader
                self._become_leader()
            else:
                # Higher nodes responded, wait for them to elect leader
                self._wait_for_coordinator()
                
        self.election_in_progress = False
        
    def _send_election_messages(self, target_nodes: Set[NodeIdentifier]) -> int:
        """Send election messages to target nodes"""
        responses = 0
        message = {
            'type': MessageType.ELECTION.value,
            'sender': str(self.node_id),
            'timestamp': time.time()
        }
        
        for node in target_nodes:
            try:
                self.socket.sendto(json.dumps(message).encode(), self.multicast_group)
                # In a real implementation, we would send directly to each node
                # For simplicity, we're using multicast
            except Exception as e:
                print(f"Failed to send election message to {node}: {e}")
                
        # Wait for responses (simplified - in reality we'd track individual responses)
        time.sleep(2.0)
        return responses
        
    def _become_leader(self):
        """Become the leader and announce to all nodes"""
        self.state = NodeState.LEADER
        self.current_leader = self.node_id
        
        print(f"👑 Node {self.node_id} became LEADER")
        
        # Send coordinator message to all nodes
        message = {
            'type': MessageType.COORDINATOR.value,
            'leader': str(self.node_id),
            'timestamp': time.time()
        }
        
        try:
            self.socket.sendto(json.dumps(message).encode(), self.multicast_group)
        except Exception as e:
            print(f"Failed to send coordinator message: {e}")
            
    def _wait_for_coordinator(self):
        """Wait for coordinator message from elected leader"""
        timeout = time.time() + self.election_timeout
        
        while time.time() < timeout and self.running:
            time.sleep(0.1)
            
        if not self.current_leader:
            print(f"⚠️  No coordinator message received, restarting election")
            self.trigger_election("coordinator_timeout")
            
    def _election_monitor(self):
        """Monitor for election messages and handle them"""
        while self.running:
            try:
                # Receive and process election messages
                data, sender_addr = self.receiver_socket.recvfrom(1024)
                message_str = data.decode().strip()
                
                # Skip our own messages
                if sender_addr[0] == self.node_id.ip:
                    continue
                
                try:
                    message = json.loads(message_str)
                    self._handle_election_message(message, sender_addr)
                except json.JSONDecodeError:
                    # Ignore non-JSON messages (could be regular server messages)
                    continue
                    
            except socket.timeout:
                # Timeout is expected, continue monitoring
                continue
            except Exception as e:
                if self.running:
                    print(f"Election monitor error: {e}")
                    
    def _handle_election_message(self, message: dict, sender_addr):
        """Handle incoming election messages"""
        msg_type = message.get('type')
        
        if msg_type == MessageType.HEARTBEAT.value:
            self._handle_heartbeat(message, sender_addr)
        elif msg_type == MessageType.ELECTION.value:
            self._handle_election_request(message, sender_addr)
        elif msg_type == MessageType.ANSWER.value:
            self._handle_election_answer(message, sender_addr)
        elif msg_type == MessageType.COORDINATOR.value:
            self._handle_coordinator_message(message, sender_addr)
        elif msg_type == MessageType.HEARTBEAT_ACK.value:
            self._handle_heartbeat_ack(message, sender_addr)
            
    def _handle_heartbeat(self, message: dict, sender_addr):
        """Handle heartbeat message from leader"""
        leader_id_str = message.get('leader')
        if leader_id_str:
            # Update last heartbeat time
            self.last_heartbeat_time = time.time()
            
            # If we don't have a leader or it's a different leader, update
            if not self.current_leader or str(self.current_leader) != leader_id_str:
                # Parse leader ID
                parts = leader_id_str.split(':')
                if len(parts) >= 3:
                    leader_ip = parts[0]
                    leader_port = int(parts[1])
                    leader_pid = int(parts[2])
                    self.current_leader = NodeIdentifier(leader_ip, leader_port, leader_pid)
                    self.state = NodeState.FOLLOWER
                    print(f"👑 Recognized leader: {self.current_leader}")
            
            # Send heartbeat ACK back to leader
            self._send_heartbeat_ack(sender_addr)
            
    def _handle_election_request(self, message: dict, sender_addr):
        """Handle election request from another node"""
        sender_id_str = message.get('sender')
        if sender_id_str:
            # Parse sender ID
            parts = sender_id_str.split(':')
            if len(parts) >= 3:
                sender_ip = parts[0]
                sender_port = int(parts[1])
                sender_pid = int(parts[2])
                sender_node = NodeIdentifier(sender_ip, sender_port, sender_pid)
                
                # If sender has lower priority, ignore
                # If sender has higher priority, send answer and start our own election
                if sender_node < self.node_id:
                    # We have higher priority, send answer
                    self._send_election_answer(sender_addr)
                    # Also start our own election if not already in progress
                    if not self.election_in_progress:
                        self.trigger_election("higher_priority_node")
                        
    def _handle_election_answer(self, message: dict, sender_addr):
        """Handle answer to our election request"""
        # Higher priority node responded, we should not become leader
        print(f"📨 Received election answer from higher priority node")
        
    def _handle_coordinator_message(self, message: dict, sender_addr):
        """Handle coordinator announcement from new leader"""
        leader_id_str = message.get('leader')
        if leader_id_str:
            # Parse leader ID
            parts = leader_id_str.split(':')
            if len(parts) >= 3:
                leader_ip = parts[0]
                leader_port = int(parts[1])
                leader_pid = int(parts[2])
                new_leader = NodeIdentifier(leader_ip, leader_port, leader_pid)
                
                self.current_leader = new_leader
                self.state = NodeState.FOLLOWER
                self.last_heartbeat_time = time.time()
                print(f"👑 New leader elected: {new_leader}")
                
    def _handle_heartbeat_ack(self, message: dict, sender_addr):
        """Handle heartbeat acknowledgment from follower"""
        # For now, just log - could be used for leader to track active followers
        pass
        
    def _send_heartbeat_ack(self, leader_addr):
        """Send heartbeat acknowledgment to leader"""
        message = {
            'type': MessageType.HEARTBEAT_ACK.value,
            'sender': str(self.node_id),
            'timestamp': time.time()
        }
        
        try:
            self.socket.sendto(json.dumps(message).encode(), leader_addr)
        except Exception as e:
            print(f"Failed to send heartbeat ACK: {e}")
            
    def _send_election_answer(self, requester_addr):
        """Send answer to election request"""
        message = {
            'type': MessageType.ANSWER.value,
            'sender': str(self.node_id),
            'timestamp': time.time()
        }
        
        try:
            self.socket.sendto(json.dumps(message).encode(), requester_addr)
        except Exception as e:
            print(f"Failed to send election answer: {e}")
                    
    def _heartbeat_monitor(self):
        """Monitor leader heartbeats and detect failures"""
        while self.running:
            try:
                if self.state == NodeState.LEADER:
                    # Send heartbeat as leader
                    self._send_heartbeat()
                else:
                    # Check if leader is alive
                    if self.current_leader and self._is_leader_dead():
                        print(f"💀 Leader {self.current_leader} appears dead")
                        self.current_leader = None
                        self.trigger_election("leader_failure")
                        
                time.sleep(self.heartbeat_interval)
                
            except Exception as e:
                if self.running:
                    print(f"Heartbeat monitor error: {e}")
                    
    def _send_heartbeat(self):
        """Send heartbeat as leader"""
        message = {
            'type': MessageType.HEARTBEAT.value,
            'leader': str(self.node_id),
            'timestamp': time.time()
        }
        
        try:
            self.socket.sendto(json.dumps(message).encode(), self.multicast_group)
        except Exception as e:
            print(f"Failed to send heartbeat: {e}")
            
    def _is_leader_dead(self) -> bool:
        """Check if current leader is dead based on heartbeat timeout"""
        return time.time() - self.last_heartbeat_time > self.heartbeat_timeout
        
    def handle_new_server_join(self, server_info: dict):
        """Handle when a new server joins the group"""
        node_id = NodeIdentifier(
            server_info['ip'],
            server_info.get('port', 5008),
            server_info.get('process_id', os.getpid())
        )
        
        added = self.group_view.add_member(node_id, server_info)
        
        if added:
            print(f"🆕 New server joined: {node_id}")
            
            # If new server has higher priority than current leader, trigger election
            if self.current_leader and node_id > self.current_leader:
                self.trigger_election("new_server_joins")
                
    def get_leader(self) -> Optional[NodeIdentifier]:
        """Get current leader"""
        return self.current_leader
        
    def get_state(self) -> NodeState:
        """Get current node state"""
        return self.state
        
    def get_group_view(self) -> GroupView:
        """Get current group view"""
        return self.group_view
        
    def is_leader(self) -> bool:
        """Check if this node is the leader"""
        return self.state == NodeState.LEADER