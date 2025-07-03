# DistributedSystems



#python env my env
# conda activate myenv 


test 123 

- MulticastSender.py: Client-side multicast communication for joining and sending messages
  - MulticastReceiver.py: Server-side multicast receiver that listens for client join requests and messages
  - Server.py: Contains IP discovery utility and system status display functions
  - Client.py: Empty file (not implemented)
  - BullyElection.py: Implements bully algorithm for leader election
  - resources/utils.py: Configuration constants and shared data structures




  ⏺ Active server discovery has been implemented with all four mechanisms:

  Added Features:

  1. Server Heartbeat System (Server.py:31-39)
    - Periodic announcements every 10 seconds
    - Broadcasts "SERVER_ALIVE:IP:hostname" messages
  2. Discovery Listener (MulticastReceiver.py:44-54)
    - Handles SERVER_ALIVE messages
    - Adds discovered servers to group_view_servers
    - Updates server_last_seen timestamps
  3. Active Server Probe (Server.py:41-59)
    - Sends SERVER_PROBE messages to discover servers
    - Listens for SERVER_RESPONSE replies
    - Adds responding servers to the group view
  4. Health Monitoring (Server.py:61-73)
    - Removes servers not seen for 30+ seconds
    - Periodic cleanup every 15 seconds
    - Maintains server_last_seen dictionary

  Usage:

  - Run python Server.py to start server discovery
  - Run python MulticastReceiver.py to listen for messages
  - Servers will automatically discover each other and maintain an active list


    1. Server startup: Server.py:111 - triggers election after initialization2. New server joins: MulticastReceiver.py:60 - triggers election when SERVER_ALIVE received3. Leader fails: Server.py:77 -
  detects failure in cleanup and triggers election

  Key files created/modified:
  - LeaderElection.py - Complete bully algorithm implementation with network communication
  - Server.py - Added election initialization and failure detection
  - MulticastReceiver.py - Added election message handling
  - resources/utils.py - Added leader state management

  The implementation uses server IDs based on IP+hostname hash, handles ELECTION/OK/COORDINATOR messages via multicast, and maintains leader state globally.