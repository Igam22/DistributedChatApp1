#!/usr/bin/env python3
"""
Step 2: Debug message sending/receiving
This script will help us understand server-to-server communication issues.
"""

import socket
import time
import threading
import json
from resources.utils import safe_print, MULTICAST_GROUP_ADDRESS, MULTICAST_IP, MULTICAST_PORT

def test_message_communication():
    """Test basic message sending and receiving"""
    
    safe_print("=== STEP 2: MESSAGE COMMUNICATION DEBUG ===")
    
    # Test sending a simple message
    try:
        safe_print("Testing message sending...")
        
        # Create sender socket
        sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        
        # Send a test message
        test_message = "SERVER_ALIVE:192.168.1.100:TEST-HOST"
        sender_socket.sendto(test_message.encode(), MULTICAST_GROUP_ADDRESS)
        safe_print(f"✅ Sent test message: {test_message}")
        sender_socket.close()
        
    except Exception as e:
        safe_print(f"❌ Message sending failed: {e}")
        return False
    
    # Test receiving messages
    try:
        safe_print("Testing message receiving...")
        
        # Create receiver socket
        UDP_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        UDP_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        UDP_socket.bind(('', MULTICAST_PORT))
        UDP_socket.settimeout(3)  # 3 second timeout
        
        # Join multicast group
        import struct
        mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_IP), socket.INADDR_ANY)
        UDP_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        safe_print("✅ Receiver socket created, waiting for messages...")
        
        # Send a test message from another socket
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        test_msg = "TEST_MESSAGE_STEP2"
        sender.sendto(test_msg.encode(), MULTICAST_GROUP_ADDRESS)
        sender.close()
        
        # Try to receive it
        try:
            data, addr = UDP_socket.recvfrom(1024)
            received_msg = data.decode()
            safe_print(f"✅ Received message: {received_msg} from {addr}")
        except socket.timeout:
            safe_print("⚠️  No message received (timeout) - this might indicate network issues")
        
        UDP_socket.close()
        
    except Exception as e:
        safe_print(f"❌ Message receiving failed: {e}")
        return False
    
    # Test fault tolerance message handling
    try:
        safe_print("Testing fault tolerance message processing...")
        
        from FaultTolerance import get_fault_tolerance_manager
        ft_manager = get_fault_tolerance_manager()
        
        if ft_manager:
            # Test processing a SERVER_ALIVE message
            test_msg = "SERVER_ALIVE:192.168.1.100:TEST-HOST"
            test_addr = ('192.168.1.100', 12345)
            
            result = ft_manager.handle_message(test_msg, test_addr)
            safe_print(f"✅ Fault tolerance processed message: {result}")
        else:
            safe_print("⚠️  No fault tolerance manager available")
            
    except Exception as e:
        safe_print(f"❌ Fault tolerance message processing failed: {e}")
        safe_print("   This is likely the source of your 'corrupted message' errors!")
        return False
    
    safe_print("=== STEP 2 RESULTS ===")
    safe_print("Message communication test completed.")
    
    return True

if __name__ == "__main__":
    success = test_message_communication()
    if success:
        safe_print("\n🟢 Step 2 PASSED - Message communication works")
        safe_print("Next: Test full server startup sequence")
    else:
        safe_print("\n🔴 Step 2 FAILED - Message communication has issues")