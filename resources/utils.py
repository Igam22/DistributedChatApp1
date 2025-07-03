#Defining Multicast variables 
MULTICAST_IP = '224.1.1.1'
MULTICAST_PORT = 5008
MULTICAST_GROUP_ADDRESS = (MULTICAST_IP, MULTICAST_PORT)
MULTICAST_TTL=2
BUFFER_SIZE = 10240

#Defining a view where we can see all the participants in the system
group_view_clients = set() 
group_view_servers = set()

# Server tracking structures
server_last_seen = {}  # Track when servers were last seen

# Leader election state
current_leader = None  # Current leader server ID
leader_election_in_progress = False  # Election status flag
my_server_id = None  # This server's ID

# Client tracking structures
client_last_seen = {}  # Track when clients were last seen

# SYSTEM CONFIGURATION CONSTANTS
# Timeout values (in seconds)
CLIENT_TIMEOUT = 60                    # How long to wait before considering client dead
SERVER_TIMEOUT = 30                    # How long to wait before considering server dead
FAILURE_DETECTION_TIMEOUT = 15         # How long to wait before detecting node failure
LEADER_HEARTBEAT_TIMEOUT = 10          # How long to wait for leader heartbeat
HEARTBEAT_INTERVAL = 5                 # How often to send heartbeat messages
DISCOVERY_TIMEOUT = 5                  # Timeout for discovery operations
SOCKET_TIMEOUT = 10                    # Default socket timeout

# Retry and attempt limits
MAX_RETRY_ATTEMPTS = 3                 # Maximum retry attempts for operations
DISCOVERY_STARTUP_TIMEOUT = 15         # Total time for startup discovery phase
RETRY_DELAY = 2                        # Delay between retry attempts

# Message reliability settings
MESSAGE_TIMEOUT = 5                    # Timeout for message acknowledgment
MAX_MESSAGE_RETRIES = 3                # Maximum message retry attempts

# Discovery intervals
SERVER_ANNOUNCE_INTERVAL = 10          # How often servers announce presence
CLEANUP_INTERVAL = 15                  # How often to run cleanup operations
PARTITION_PROBE_INTERVAL = 10          # How often to probe for partitions

# Buffer and communication settings
SOCKET_BUFFER_SIZE = 1024              # Standard socket buffer size
LARGE_BUFFER_SIZE = 10240              # Large buffer for multicast operations

import socket
import uuid
import hashlib

def generate_server_id(server_ip: str, hostname: str = None) -> int:
    """
    Generate consistent server ID using IP address and hostname.
    
    Args:
        server_ip: The server's IP address
        hostname: The server's hostname (optional, will use current hostname if not provided)
    
    Returns:
        Integer server ID between 0 and 9999
    """
    if hostname is None:
        hostname = socket.gethostname()
    
    # Create consistent server ID using hash of IP + hostname
    id_string = f"{server_ip}:{hostname}"
    hash_value = hashlib.sha256(id_string.encode()).hexdigest()
    return int(hash_value[:8], 16) % 10000

def generate_client_id(username: str = None) -> str:
    """
    Generate unique client ID using username and UUID.
    
    Args:
        username: Client username (optional, will generate random if not provided)
    
    Returns:
        Unique client ID string
    """
    if username is None:
        username = f"User_{uuid.uuid4().hex[:8]}"
    
    unique_suffix = uuid.uuid4().hex[:8]
    return f"{username}_{unique_suffix}"

def create_message(msg_type: str, sender_id: str, payload: dict = None, **kwargs) -> dict:
    """
    Create standardized message format.
    
    Args:
        msg_type: Type of message (SERVER_ALIVE, CLIENT_JOIN, etc.)
        sender_id: ID of the sender
        payload: Message payload data
        **kwargs: Additional message fields
    
    Returns:
        Standardized message dictionary
    """
    import time
    
    message = {
        'type': msg_type,
        'sender_id': sender_id,
        'timestamp': time.time(),
        'payload': payload or {}
    }
    
    # Add any additional fields
    message.update(kwargs)
    
    return message

def create_socket_with_timeout(timeout: int = SOCKET_TIMEOUT) -> socket.socket:
    """
    Create UDP socket with standard configuration.
    
    Args:
        timeout: Socket timeout in seconds
    
    Returns:
        Configured UDP socket
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock

def create_multicast_socket(ttl: int = MULTICAST_TTL) -> socket.socket:
    """
    Create multicast socket with standard configuration.
    
    Args:
        ttl: Multicast Time-To-Live value
    
    Returns:
        Configured multicast socket
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock
