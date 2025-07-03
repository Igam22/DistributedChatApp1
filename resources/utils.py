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
