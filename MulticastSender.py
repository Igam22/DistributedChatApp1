import socket
import threading
import pickle

from resources.utils import MULTICAST_GROUP_ADDRESS
from resources.utils import MULTICAST_IP
from resources.utils import MULTICAST_PORT
from resources.utils import BUFFER_SIZE
from resources.utils import MULTICAST_TTL
from resources.utils import group_view_clients

# Creating UDP socket instance 
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
client_socket.settimeout(3)

# Letting other clients join more dynamically 
join_message = "join"
client_socket.sendto(join_message.encode(), MULTICAST_GROUP_ADDRESS)
print(f"\nClient sent a join request to {MULTICAST_GROUP_ADDRESS}")
try:
    
    data, addr = client_socket.recvfrom(BUFFER_SIZE)
    print(f"\nClient Received from {addr}: {data.decode()}")
    if addr not in group_view_clients:
            group_view_clients.add(addr)
            print(f"Client {addr} added to clients_server set.")
    else:
            print(f"Client {addr} already in clients_server set.")
except socket.timeout:
    print("\nClient No response to join request")
    client_socket.close()
    exit()


client_socket.settimeout(3000)

#Allowing Clients to send messages in Multicast
def send_messages():
    try:
            while True:
                message = input("\nSend message or type exit: ")
                if message.lower() == 'exit':
                    break
                client_socket.sendto(message.encode(), MULTICAST_GROUP_ADDRESS)
    except KeyboardInterrupt:
            client_socket.close()
    except socket.timeout:
            print("\nTimeout: no response")
            client_socket.close()

#Allowing Clients to receive messages in Multicast
def receive_messages():
    while True:
        try:
            data, server = client_socket.recvfrom(BUFFER_SIZE)
            print(f"\nReceived message from {server}: {data.decode()}")
        except socket.timeout:
            print("\nTimeout: no response")
            break
        except KeyboardInterrupt:
            break


#Das kommt nachher in server!!!
if __name__ == "__main__":
    receiver_thread = threading.Thread(target=receive_messages, daemon=True)
    receiver_thread.start()
    #print(print_lock)
    send_messages()

    client_socket.close()
   



