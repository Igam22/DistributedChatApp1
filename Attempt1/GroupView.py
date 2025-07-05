import time
import threading
from typing import Dict, Set, List, Optional, Tuple
from resources.utils import group_view_servers, group_view_clients, server_last_seen, current_leader, safe_print

class Participant:
    """Represents a participant in the distributed system"""
    def __init__(self, participant_id: str, participant_type: str, address: Tuple[str, int], 
                 hostname: str = None, join_time: float = None):
        self.id = participant_id
        self.type = participant_type  # 'server' or 'client'
        self.address = address
        self.hostname = hostname
        self.join_time = join_time or time.time()
        self.last_seen = time.time()
        self.is_active = True
        self.metadata = {}
    
    def update_activity(self):
        """Update last seen timestamp"""
        self.last_seen = time.time()
        self.is_active = True
    
    def mark_inactive(self):
        """Mark participant as inactive"""
        self.is_active = False
    
    def to_dict(self):
        """Convert participant to dictionary representation"""
        return {
            'id': self.id,
            'type': self.type,
            'address': self.address,
            'hostname': self.hostname,
            'join_time': self.join_time,
            'last_seen': self.last_seen,
            'is_active': self.is_active,
            'uptime': time.time() - self.join_time,
            'metadata': self.metadata
        }

class GroupView:
    """Unified group view manager for all participants in the distributed system"""
    
    def __init__(self, server_timeout: int = 30, client_timeout: int = 60):
        self.participants: Dict[str, Participant] = {}
        self.server_timeout = server_timeout
        self.client_timeout = client_timeout
        self.event_callbacks = []
        self.cleanup_thread = None
        self.running = False
        self.lock = threading.Lock()
    
    def start(self):
        """Start the group view manager"""
        self.running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
    
    def stop(self):
        """Stop the group view manager"""
        self.running = False
        if self.cleanup_thread:
            self.cleanup_thread.join()
    
    def add_participant(self, participant_id: str, participant_type: str, 
                       address: Tuple[str, int], hostname: str = None) -> bool:
        """Add a new participant to the group view"""
        with self.lock:
            if participant_id in self.participants:
                # Update existing participant
                self.participants[participant_id].update_activity()
                return False
            else:
                # Add new participant
                participant = Participant(participant_id, participant_type, address, hostname)
                self.participants[participant_id] = participant
                self._notify_event('join', participant)
                return True
    
    def remove_participant(self, participant_id: str) -> bool:
        """Remove a participant from the group view"""
        with self.lock:
            if participant_id in self.participants:
                participant = self.participants.pop(participant_id)
                self._notify_event('leave', participant)
                return True
            return False
    
    def update_participant_activity(self, participant_id: str):
        """Update participant's last seen timestamp"""
        with self.lock:
            if participant_id in self.participants:
                self.participants[participant_id].update_activity()
    
    def get_participant(self, participant_id: str) -> Optional[Participant]:
        """Get a specific participant by ID"""
        with self.lock:
            return self.participants.get(participant_id)
    
    def get_all_participants(self) -> List[Participant]:
        """Get all participants"""
        with self.lock:
            return list(self.participants.values())
    
    def get_active_participants(self) -> List[Participant]:
        """Get only active participants"""
        with self.lock:
            return [p for p in self.participants.values() if p.is_active]
    
    def get_servers(self) -> List[Participant]:
        """Get all server participants"""
        with self.lock:
            return [p for p in self.participants.values() if p.type == 'server']
    
    def get_clients(self) -> List[Participant]:
        """Get all client participants"""
        with self.lock:
            return [p for p in self.participants.values() if p.type == 'client']
    
    def get_active_servers(self) -> List[Participant]:
        """Get active server participants"""
        with self.lock:
            return [p for p in self.participants.values() if p.type == 'server' and p.is_active]
    
    def get_active_clients(self) -> List[Participant]:
        """Get active client participants"""
        with self.lock:
            return [p for p in self.participants.values() if p.type == 'client' and p.is_active]
    
    def get_participant_count(self) -> Dict[str, int]:
        """Get count of participants by type"""
        with self.lock:
            counts = {'servers': 0, 'clients': 0, 'active_servers': 0, 'active_clients': 0}
            for participant in self.participants.values():
                if participant.type == 'server':
                    counts['servers'] += 1
                    if participant.is_active:
                        counts['active_servers'] += 1
                elif participant.type == 'client':
                    counts['clients'] += 1
                    if participant.is_active:
                        counts['active_clients'] += 1
            return counts
    
    def get_leader_info(self) -> Optional[Dict]:
        """Get current leader information"""
        if current_leader:
            leader = self.get_participant(str(current_leader))
            if leader:
                return leader.to_dict()
        return None
    
    def search_participants(self, query: str) -> List[Participant]:
        """Search participants by hostname or ID"""
        with self.lock:
            results = []
            query_lower = query.lower()
            for participant in self.participants.values():
                if (query_lower in participant.id.lower() or 
                    (participant.hostname and query_lower in participant.hostname.lower())):
                    results.append(participant)
            return results
    
    def get_system_status(self) -> Dict:
        """Get comprehensive system status"""
        with self.lock:
            counts = self.get_participant_count()
            leader_info = self.get_leader_info()
            
            return {
                'timestamp': time.time(),
                'participant_counts': counts,
                'total_participants': len(self.participants),
                'active_participants': len(self.get_active_participants()),
                'current_leader': leader_info,
                'participants': [p.to_dict() for p in self.participants.values()]
            }
    
    def add_event_callback(self, callback):
        """Add event callback for join/leave notifications"""
        self.event_callbacks.append(callback)
    
    def _notify_event(self, event_type: str, participant: Participant):
        """Notify all event callbacks"""
        for callback in self.event_callbacks:
            try:
                callback(event_type, participant)
            except Exception as e:
                safe_print(f"Error in event callback: {e}")
    
    def _cleanup_loop(self):
        """Background cleanup loop for inactive participants"""
        while self.running:
            time.sleep(15)  # Check every 15 seconds
            self._cleanup_inactive_participants()
    
    def _cleanup_inactive_participants(self):
        """Remove participants that haven't been seen recently"""
        current_time = time.time()
        inactive_participants = []
        
        with self.lock:
            for participant in self.participants.values():
                timeout = self.server_timeout if participant.type == 'server' else self.client_timeout
                if current_time - participant.last_seen > timeout:
                    inactive_participants.append(participant.id)
            
            for participant_id in inactive_participants:
                if participant_id in self.participants:
                    participant = self.participants.pop(participant_id)
                    safe_print(f"Removed inactive {participant.type}: {participant.id}")
                    self._notify_event('timeout', participant)
    
    def sync_with_legacy_views(self):
        """Synchronize with existing group_view_servers and group_view_clients"""
        # Sync servers
        for server_id in group_view_servers.copy():
            if str(server_id) not in self.participants:
                self.add_participant(str(server_id), 'server', ('unknown', 0))
        
        # Sync clients
        for client_addr in group_view_clients.copy():
            client_id = f"{client_addr[0]}:{client_addr[1]}"
            if client_id not in self.participants:
                self.add_participant(client_id, 'client', client_addr)
        
        # Update server timestamps from server_last_seen
        for server_id, last_seen in server_last_seen.items():
            if str(server_id) in self.participants:
                self.participants[str(server_id)].last_seen = last_seen

# Global group view instance
group_view = GroupView()

def get_group_view() -> GroupView:
    """Get the global group view instance"""
    return group_view

def start_group_view():
    """Start the global group view manager"""
    group_view.start()

def stop_group_view():
    """Stop the global group view manager"""
    group_view.stop()

def print_system_status():
    """Print comprehensive system status"""
    status = group_view.get_system_status()
    safe_print("\n" + "="*50)
    safe_print("DISTRIBUTED SYSTEM STATUS")
    safe_print("="*50)
    safe_print(f"Total Participants: {status['total_participants']}")
    safe_print(f"Active Participants: {status['active_participants']}")
    safe_print(f"Servers: {status['participant_counts']['active_servers']}/{status['participant_counts']['servers']}")
    safe_print(f"Clients: {status['participant_counts']['active_clients']}/{status['participant_counts']['clients']}")
    
    leader_info = status['current_leader']
    if leader_info:
        safe_print(f"Current Leader: {leader_info['hostname']} (ID: {leader_info['id']})")
    else:
        safe_print("Current Leader: None")
    
    safe_print("\nACTIVE PARTICIPANTS:")
    safe_print("-" * 50)
    for participant in status['participants']:
        if participant['is_active']:
            uptime = int(participant['uptime'])
            safe_print(f"{participant['type'].upper()}: {participant['id']} "
                  f"({participant['hostname']}) - Uptime: {uptime}s")
    
    safe_print("="*50)