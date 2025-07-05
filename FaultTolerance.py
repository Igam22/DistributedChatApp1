import socket
import threading
import time
import json
import hashlib
import uuid
from typing import Dict, Set, Optional, Callable, Any, Tuple
from collections import defaultdict, deque
from resources.utils import MULTICAST_GROUP_ADDRESS, group_view_servers, current_leader, safe_print

# Thread-safe logging using safe_print
# Log levels: DEBUG, INFO, WARNING, ERROR
def safe_log(level, message):
    """Thread-safe logging function"""
    safe_print(f"[{level}] {message}")

class MessageType:
    """Message types for fault tolerance"""
    HEARTBEAT = "HEARTBEAT"
    ACK = "ACK"
    RELIABLE_MSG = "RELIABLE_MSG"
    LEADER_HEARTBEAT = "LEADER_HEARTBEAT"
    PARTITION_PROBE = "PARTITION_PROBE"
    RECOVERY_REQUEST = "RECOVERY_REQUEST"
    STATE_SYNC = "STATE_SYNC"

class FaultType:
    """Fault types for monitoring"""
    CRASH = "crash"
    OMISSION = "omission"
    BYZANTINE = "byzantine"
    PARTITION = "partition"

class ReliableMessage:
    """Reliable message with sequence number and acknowledgment"""
    def __init__(self, sender_id: str, msg_type: str, payload: Any, msg_id: str = None):
        self.msg_id = msg_id or str(uuid.uuid4())
        self.sender_id = sender_id
        self.msg_type = msg_type
        self.payload = payload
        self.timestamp = time.time()
        self.sequence_num = 0
        self.checksum = self._calculate_checksum()
        self.retry_count = 0
        self.max_retries = 3
        
    def _calculate_checksum(self) -> str:
        """Calculate message checksum for integrity"""
        data = f"{self.sender_id}{self.msg_type}{str(self.payload)}{self.timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def verify_integrity(self) -> bool:
        """Verify message integrity"""
        expected_checksum = self._calculate_checksum()
        return self.checksum == expected_checksum
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for transmission"""
        return {
            'msg_id': self.msg_id,
            'sender_id': self.sender_id,
            'msg_type': self.msg_type,
            'payload': self.payload,
            'timestamp': self.timestamp,
            'sequence_num': self.sequence_num,
            'checksum': self.checksum
        }
    
    @classmethod
    def from_dict(cls, data: Dict):
        """Create from dictionary"""
        msg = cls(data['sender_id'], data['msg_type'], data['payload'], data['msg_id'])
        msg.timestamp = data['timestamp']
        msg.sequence_num = data['sequence_num']
        msg.checksum = data['checksum']
        return msg

class PartitionDetector:
    """Network partition detection and recovery"""
    def __init__(self, node_id: str, probe_interval: int = 10):
        self.node_id = node_id
        self.probe_interval = probe_interval
        self.known_nodes: Set[str] = set()
        self.reachable_nodes: Set[str] = set()
        self.partition_start_time: Optional[float] = None
        self.in_partition = False
        self.probe_responses: Dict[str, float] = {}
        
        # Startup grace period to prevent false partition detection during startup
        self.startup_time = time.time()
        self.startup_grace_period = 30  # 30 seconds grace period
        self.partition_detection_enabled = False
        
    def add_known_node(self, node_id: str):
        """Add a node to the known nodes list"""
        self.known_nodes.add(node_id)
        
    def probe_nodes(self) -> bool:
        """Probe all known nodes to detect partitions"""
        self.reachable_nodes.clear()
        
        # Check if we're still in startup grace period
        current_time = time.time()
        if not self.partition_detection_enabled:
            if current_time - self.startup_time < self.startup_grace_period:
                # Still in startup grace period, don't detect partitions yet
                safe_log("DEBUG", f"Partition detection disabled - still in startup grace period ({int(self.startup_grace_period - (current_time - self.startup_time))}s remaining)")
                self.in_partition = False
                return True
            else:
                # Grace period ended, enable partition detection
                self.partition_detection_enabled = True
                safe_log("INFO", "Startup grace period ended - enabling partition detection")
        
        # If we don't know about any other nodes yet, we're not in a partition
        total_nodes = len(self.known_nodes)
        if total_nodes == 0:
            self.in_partition = False
            return True  # Single node is always connected
        
        # Probe all known nodes
        for node_id in self.known_nodes:
            if self._probe_node(node_id):
                self.reachable_nodes.add(node_id)
                self.probe_responses[node_id] = time.time()
        
        # Check if we're in a partition (need majority of known nodes)
        reachable_nodes = len(self.reachable_nodes)
        partition_threshold = total_nodes * 0.5  # Majority
        
        was_in_partition = self.in_partition
        self.in_partition = reachable_nodes < partition_threshold
        
        # Only log partition events if we actually have other nodes to connect to
        if total_nodes > 1:  # Only check partitions when we have multiple nodes
            if self.in_partition and not was_in_partition:
                self.partition_start_time = time.time()
                safe_log("WARNING", f"Network partition detected! Reachable: {reachable_nodes}/{total_nodes}")
            elif not self.in_partition and was_in_partition:
                safe_log("INFO", f"Partition healed! Reachable: {reachable_nodes}/{total_nodes}")
                self.partition_start_time = None
        
        return not self.in_partition
    
    def _probe_node(self, node_id: str) -> bool:
        """Probe a specific node"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Increased timeout to 5 seconds to prevent timing out on servers still initializing
            sock.settimeout(5)
            
            probe_msg = {
                'type': MessageType.PARTITION_PROBE,
                'sender_id': self.node_id,
                'target_id': node_id,
                'timestamp': time.time()
            }
            
            sock.sendto(json.dumps(probe_msg).encode(), MULTICAST_GROUP_ADDRESS)
            
            # Wait for response
            response, addr = sock.recvfrom(1024)
            response_data = json.loads(response.decode())
            
            if (response_data.get('type') == MessageType.PARTITION_PROBE and 
                response_data.get('target_id') == self.node_id):
                return True
                
        except Exception as e:
            safe_log("DEBUG", f"Failed to probe node {node_id}: {e}")
        finally:
            sock.close()
        
        return False

class FaultToleranceManager:
    """Comprehensive fault tolerance manager"""
    
    def __init__(self, node_id: str, node_type: str = "server"):
        self.node_id = node_id
        self.node_type = node_type
        
        # Message reliability
        self.pending_messages: Dict[str, ReliableMessage] = {}
        self.received_messages: Set[str] = set()
        self.sequence_counter = 0
        self.message_timeout = 5  # seconds
        
        # Failure detection
        self.heartbeat_interval = 5  # seconds
        self.failure_timeout = 15  # seconds
        self.node_last_seen: Dict[str, float] = {}
        self.failed_nodes: Set[str] = set()
        
        # Partition detection
        self.partition_detector = PartitionDetector(node_id)
        
        # Recovery mechanisms
        self.recovery_callbacks: Dict[str, Callable] = {}
        self.state_backup: Dict[str, Any] = {}
        
        # Threading
        self.running = False
        self.threads: Dict[str, threading.Thread] = {}
        
        # Statistics
        self.fault_stats = {
            FaultType.CRASH: 0,
            FaultType.OMISSION: 0,
            FaultType.BYZANTINE: 0,
            FaultType.PARTITION: 0
        }
        
        # Leader monitoring (for servers)
        self.leader_last_seen: Optional[float] = None
        self.leader_timeout = 10  # seconds
        
    def start(self):
        """Start fault tolerance mechanisms"""
        if self.running:
            return
            
        self.running = True
        safe_log("INFO", f"Starting fault tolerance for {self.node_type} {self.node_id}")
        
        # Start threads
        self.threads['heartbeat'] = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.threads['failure_detector'] = threading.Thread(target=self._failure_detection_loop, daemon=True)
        self.threads['message_timeout'] = threading.Thread(target=self._message_timeout_loop, daemon=True)
        self.threads['partition_detector'] = threading.Thread(target=self._partition_detection_loop, daemon=True)
        
        if self.node_type == "server":
            self.threads['leader_monitor'] = threading.Thread(target=self._leader_monitoring_loop, daemon=True)
        
        for thread in self.threads.values():
            thread.start()
    
    def stop(self):
        """Stop fault tolerance mechanisms"""
        self.running = False
        for thread in self.threads.values():
            thread.join(timeout=1)
        safe_log("INFO", f"Stopped fault tolerance for {self.node_id}")
    
    def send_reliable_message(self, msg_type: str, payload: Any, target_nodes: Set[str] = None) -> str:
        """Send a reliable message with acknowledgment"""
        message = ReliableMessage(self.node_id, msg_type, payload)
        message.sequence_num = self._get_next_sequence()
        
        self.pending_messages[message.msg_id] = message
        
        # Send message
        self._transmit_message(message, target_nodes)
        
        safe_log("DEBUG", f"Sent reliable message {message.msg_id} type {msg_type}")
        return message.msg_id
    
    def handle_message(self, raw_message: str, sender_addr: Tuple[str, int]) -> Optional[Dict]:
        """Handle incoming message with fault tolerance"""
        try:
            data = json.loads(raw_message)
            
            # Handle different message types
            msg_type = data.get('type', '')
            
            if msg_type == MessageType.HEARTBEAT:
                return self._handle_heartbeat(data, sender_addr)
            elif msg_type == MessageType.ACK:
                return self._handle_acknowledgment(data)
            elif msg_type == MessageType.RELIABLE_MSG:
                return self._handle_reliable_message(data, sender_addr)
            elif msg_type == MessageType.LEADER_HEARTBEAT:
                return self._handle_leader_heartbeat(data)
            elif msg_type == MessageType.PARTITION_PROBE:
                return self._handle_partition_probe(data, sender_addr)
            else:
                # Regular message - add basic validation
                if self._validate_message(data):
                    return data
                else:
                    safe_log("WARNING", f"Invalid message from {sender_addr}: {data}")
                    self.fault_stats[FaultType.BYZANTINE] += 1
                    
        except json.JSONDecodeError:
            safe_log("WARNING", f"Corrupted message from {sender_addr}: {raw_message}")
            self.fault_stats[FaultType.BYZANTINE] += 1
        except Exception as e:
            safe_log("ERROR", f"Error handling message from {sender_addr}: {e}")
            self.fault_stats[FaultType.OMISSION] += 1
        
        return None
    
    def register_recovery_callback(self, fault_type: str, callback: Callable):
        """Register recovery callback for fault type"""
        self.recovery_callbacks[fault_type] = callback
    
    def backup_state(self, key: str, value: Any):
        """Backup state for recovery"""
        self.state_backup[key] = {
            'value': value,
            'timestamp': time.time()
        }
    
    def restore_state(self, key: str) -> Optional[Any]:
        """Restore state from backup"""
        if key in self.state_backup:
            return self.state_backup[key]['value']
        return None
    
    def _get_next_sequence(self) -> int:
        """Get next sequence number"""
        self.sequence_counter += 1
        return self.sequence_counter
    
    def _transmit_message(self, message: ReliableMessage, target_nodes: Set[str] = None):
        """Transmit message over network"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            msg_data = {
                'type': MessageType.RELIABLE_MSG,
                'message': message.to_dict(),
                'target_nodes': list(target_nodes) if target_nodes else None
            }
            
            sock.sendto(json.dumps(msg_data).encode(), MULTICAST_GROUP_ADDRESS)
            sock.close()
            
        except Exception as e:
            safe_log("ERROR", f"Failed to transmit message {message.msg_id}: {e}")
            self.fault_stats[FaultType.OMISSION] += 1
    
    def _handle_heartbeat(self, data: Dict, sender_addr: Tuple[str, int]) -> Dict:
        """Handle heartbeat message"""
        sender_id = data.get('sender_id')
        if sender_id:
            self.node_last_seen[sender_id] = time.time()
            self.partition_detector.add_known_node(sender_id)
            
            # Remove from failed nodes if it was there
            self.failed_nodes.discard(sender_id)
        
        return {'type': 'heartbeat_ack', 'sender_id': self.node_id}
    
    def _handle_acknowledgment(self, data: Dict) -> None:
        """Handle message acknowledgment"""
        msg_id = data.get('msg_id')
        if msg_id and msg_id in self.pending_messages:
            del self.pending_messages[msg_id]
            safe_log("DEBUG", f"Received ACK for message {msg_id}")
    
    def _handle_reliable_message(self, data: Dict, sender_addr: Tuple[str, int]) -> Optional[Dict]:
        """Handle reliable message"""
        try:
            message_data = data.get('message', {})
            message = ReliableMessage.from_dict(message_data)
            
            # Check for duplicate
            if message.msg_id in self.received_messages:
                safe_log("DEBUG", f"Duplicate message {message.msg_id} from {message.sender_id}")
                # Send ACK anyway
                self._send_ack(message.msg_id, sender_addr)
                return None
            
            # Verify integrity
            if not message.verify_integrity():
                safe_log("WARNING", f"Message integrity check failed for {message.msg_id}")
                self.fault_stats[FaultType.BYZANTINE] += 1
                return None
            
            # Mark as received
            self.received_messages.add(message.msg_id)
            
            # Send acknowledgment
            self._send_ack(message.msg_id, sender_addr)
            
            safe_log("DEBUG", f"Received reliable message {message.msg_id} from {message.sender_id}")
            return {
                'type': 'reliable_message',
                'message': message,
                'sender_addr': sender_addr
            }
            
        except Exception as e:
            safe_log("ERROR", f"Error handling reliable message: {e}")
            self.fault_stats[FaultType.OMISSION] += 1
            return None
    
    def _handle_leader_heartbeat(self, data: Dict) -> None:
        """Handle leader heartbeat"""
        leader_id = data.get('sender_id')
        if leader_id == current_leader:
            self.leader_last_seen = time.time()
            safe_log("DEBUG", f"Received leader heartbeat from {leader_id}")
    
    def _handle_partition_probe(self, data: Dict, sender_addr: Tuple[str, int]) -> Dict:
        """Handle partition probe"""
        target_id = data.get('target_id')
        sender_id = data.get('sender_id')
        
        if target_id == self.node_id:
            # Send response
            response = {
                'type': MessageType.PARTITION_PROBE,
                'sender_id': self.node_id,
                'target_id': sender_id,
                'timestamp': time.time()
            }
            return response
        
        return None
    
    def _send_ack(self, msg_id: str, sender_addr: Tuple[str, int]):
        """Send acknowledgment"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            ack_data = {
                'type': MessageType.ACK,
                'msg_id': msg_id,
                'sender_id': self.node_id
            }
            sock.sendto(json.dumps(ack_data).encode(), MULTICAST_GROUP_ADDRESS)
            sock.close()
            
        except Exception as e:
            safe_log("ERROR", f"Failed to send ACK for {msg_id}: {e}")
    
    def _validate_message(self, data: Dict) -> bool:
        """Basic message validation"""
        required_fields = ['type', 'sender_id']
        return all(field in data for field in required_fields)
    
    def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self.running:
            try:
                heartbeat_data = {
                    'type': MessageType.HEARTBEAT,
                    'sender_id': self.node_id,
                    'node_type': self.node_type,
                    'timestamp': time.time()
                }
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(json.dumps(heartbeat_data).encode(), MULTICAST_GROUP_ADDRESS)
                sock.close()
                
                # Send leader heartbeat if we're the leader
                if self.node_type == "server" and current_leader == int(self.node_id):
                    leader_heartbeat = {
                        'type': MessageType.LEADER_HEARTBEAT,
                        'sender_id': self.node_id,
                        'timestamp': time.time()
                    }
                    
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.sendto(json.dumps(leader_heartbeat).encode(), MULTICAST_GROUP_ADDRESS)
                    sock.close()
                
                time.sleep(self.heartbeat_interval)
                
            except Exception as e:
                safe_log("ERROR", f"Error in heartbeat loop: {e}")
                time.sleep(self.heartbeat_interval)
    
    def _failure_detection_loop(self):
        """Detect node failures"""
        while self.running:
            current_time = time.time()
            newly_failed = set()
            
            for node_id, last_seen in list(self.node_last_seen.items()):
                if current_time - last_seen > self.failure_timeout:
                    if node_id not in self.failed_nodes:
                        newly_failed.add(node_id)
                        self.failed_nodes.add(node_id)
                        self.fault_stats[FaultType.CRASH] += 1
                        safe_log("WARNING", f"Node {node_id} failed (timeout)")
                        
                        # Trigger recovery callback
                        if FaultType.CRASH in self.recovery_callbacks:
                            try:
                                self.recovery_callbacks[FaultType.CRASH](node_id)
                            except Exception as e:
                                safe_log("ERROR", f"Error in crash recovery callback: {e}")
            
            time.sleep(5)  # Check every 5 seconds
    
    def _message_timeout_loop(self):
        """Handle message timeouts and retries"""
        while self.running:
            current_time = time.time()
            timed_out_messages = []
            
            for msg_id, message in list(self.pending_messages.items()):
                if current_time - message.timestamp > self.message_timeout:
                    if message.retry_count < message.max_retries:
                        # Retry message
                        message.retry_count += 1
                        message.timestamp = current_time
                        self._transmit_message(message)
                        safe_log("DEBUG", f"Retrying message {msg_id} (attempt {message.retry_count})")
                    else:
                        # Message failed
                        timed_out_messages.append(msg_id)
                        self.fault_stats[FaultType.OMISSION] += 1
                        safe_log("WARNING", f"Message {msg_id} failed after {message.max_retries} retries")
            
            # Remove failed messages
            for msg_id in timed_out_messages:
                del self.pending_messages[msg_id]
            
            time.sleep(2)  # Check every 2 seconds
    
    def _partition_detection_loop(self):
        """Detect network partitions"""
        while self.running:
            try:
                is_connected = self.partition_detector.probe_nodes()
                
                if not is_connected and self.partition_detector.in_partition:
                    self.fault_stats[FaultType.PARTITION] += 1
                    
                    # Trigger partition recovery
                    if FaultType.PARTITION in self.recovery_callbacks:
                        try:
                            self.recovery_callbacks[FaultType.PARTITION](self.partition_detector)
                        except Exception as e:
                            safe_log("ERROR", f"Error in partition recovery callback: {e}")
                
                time.sleep(self.partition_detector.probe_interval)
                
            except Exception as e:
                safe_log("ERROR", f"Error in partition detection: {e}")
                time.sleep(self.partition_detector.probe_interval)
    
    def _leader_monitoring_loop(self):
        """Monitor leader health (for servers)"""
        while self.running:
            if current_leader and self.leader_last_seen:
                if time.time() - self.leader_last_seen > self.leader_timeout:
                    safe_log("WARNING", f"Leader {current_leader} heartbeat timeout")
                    
                    # Trigger leader failure recovery
                    if FaultType.CRASH in self.recovery_callbacks:
                        try:
                            self.recovery_callbacks[FaultType.CRASH](current_leader)
                        except Exception as e:
                            safe_log("ERROR", f"Error in leader failure recovery: {e}")
            
            time.sleep(self.leader_timeout / 2)
    
    def get_fault_statistics(self) -> Dict:
        """Get fault tolerance statistics"""
        return {
            'fault_counts': self.fault_stats.copy(),
            'pending_messages': len(self.pending_messages),
            'failed_nodes': list(self.failed_nodes),
            'partition_status': {
                'in_partition': self.partition_detector.in_partition,
                'reachable_nodes': len(self.partition_detector.reachable_nodes),
                'total_known_nodes': len(self.partition_detector.known_nodes)
            },
            'leader_status': {
                'last_seen': self.leader_last_seen,
                'timeout_threshold': self.leader_timeout
            }
        }

# Global fault tolerance manager
fault_tolerance_manager: Optional[FaultToleranceManager] = None

def initialize_fault_tolerance(node_id: str, node_type: str = "server") -> FaultToleranceManager:
    """Initialize global fault tolerance manager"""
    global fault_tolerance_manager
    fault_tolerance_manager = FaultToleranceManager(node_id, node_type)
    return fault_tolerance_manager

def get_fault_tolerance_manager() -> Optional[FaultToleranceManager]:
    """Get global fault tolerance manager"""
    return fault_tolerance_manager