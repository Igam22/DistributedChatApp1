import socket
from resources.utils import group_view_servers
from resources.utils import group_view_clients

# Getting the IP address by trying to reach unreachable address, method from:https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib 
def getIP():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('10.254.254.254', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

# Defining server attributes 
server_IP= getIP()
current_leader = None 






def showSystemcomponents():
    print(f'Servers in System: {group_view_servers}')
    #print(f'Leading Server: {TODO!!!!!}')
    print(f'Clients in System: {group_view_clients}')
    

if __name__ == '__main__':