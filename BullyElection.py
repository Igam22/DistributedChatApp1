import socket
from resources.utils import group_view_servers


# Implementing a Bully leader election algorithm, method from: https://github.com/KimaruThagna/BullyAlgorithm/blob/master/bully.py 
def process_Pool(id,message_case=0):
    
    if message_case==1: # sending the election request, message=election
        highest_node=[]
        for x in group_view_servers:
            if id<x:
                highest_node.append(x) 

        if id==len(group_view_servers): # last node in the list
             return None # theres no higher priority node

        return highest_node # return list of higher priority nodes
    if message_case==2 and id is not 1:#sending an ok mesage within the time limit
        servers_list = sorted(list(group_view_servers))
        return [servers_list[int(id)-2] ]# return id of predecessor node in priority hierachy
    if message_case==3: #sending an Ive won message to other nodes
        servers_list = sorted(list(group_view_servers))
        return [x for x in servers_list if x != id] # return all nodes except the winner


#simulate communication of nodes
def sending_data(recepients,message): # recepients list and message to be sent

    if recepients is not None:# no empty list
        for node in recepients:
            print(message+" sent to Node"+str(node)) # emulate send message via print

# Construct a node
def node(myId):
    sending_list=process_Pool(myId,1)
    if  sending_list is None: # meaning no node is higher and thus, this node has won
        sending_data(process_Pool(myId,3),"I've won") # when the highest node wins
    else :
        sending_data(sending_list,"Election") # forward an election message to your successor in the priority list
    sending_data(process_Pool(myId,2),"OK") #send data to your predecessor in the priority list

#Initialize program by simulating the starting of nodes
# by calling the node function
node(1)
node(2)
node(3)
node(4)
node(5)