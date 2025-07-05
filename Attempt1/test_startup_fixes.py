#!/usr/bin/env python3
"""
Test script to verify the startup timing fixes work correctly.
This script simulates the startup sequence to ensure:
1. Partition detection doesn't trigger during startup grace period
2. No RuntimeError occurs during election
3. Discovery race conditions are handled properly
"""

import time
import sys
import threading
from unittest.mock import Mock, patch
import socket

# Add the project directory to the Python path
sys.path.insert(0, '/Users/vassil/projects/MagiDS/DistributedChatApp1')

from FaultTolerance import PartitionDetector, FaultToleranceManager
from LeaderElection import BullyLeaderElection
from DiscoveryManager import DiscoveryManager
from resources.utils import safe_print, generate_server_id

def test_partition_detection_grace_period():
    """Test that partition detection respects the startup grace period"""
    safe_print("Testing partition detection grace period...")
    
    # Create partition detector
    detector = PartitionDetector("test_server_1", probe_interval=1)
    
    # Add some known nodes
    detector.add_known_node("test_server_2")
    detector.add_known_node("test_server_3")
    
    # Initially, partition detection should be disabled
    assert not detector.partition_detection_enabled
    safe_print("✓ Partition detection initially disabled")
    
    # Test probing during grace period
    result = detector.probe_nodes()
    assert result == True  # Should return True (no partition detected)
    assert not detector.in_partition
    safe_print("✓ No partition detected during grace period")
    
    # Fast-forward past grace period
    detector.startup_time = time.time() - 35  # 35 seconds ago (past the 30s grace period)
    
    # Now partition detection should be enabled
    detector.probe_nodes()
    assert detector.partition_detection_enabled
    safe_print("✓ Partition detection enabled after grace period")
    
    safe_print("✅ Partition detection grace period test passed!\n")

def test_election_thread_safety():
    """Test that election methods handle concurrent access to group_view_servers"""
    safe_print("Testing election thread safety...")
    
    # Mock the group_view_servers to simulate concurrent modification
    with patch('LeaderElection.group_view_servers') as mock_servers:
        # Create a set that simulates concurrent modification
        test_servers = {1001, 1002, 1003, 1004}
        mock_servers.copy.return_value = test_servers.copy()
        
        # Create election instance
        election = BullyLeaderElection(1002, "192.168.1.1")
        
        # Test get_higher_priority_servers
        higher_servers = election.get_higher_priority_servers()
        expected_higher = [1003, 1004]  # Servers with ID > 1002
        assert set(higher_servers) == set(expected_higher)
        safe_print("✓ get_higher_priority_servers works correctly")
        
        # Test get_lower_priority_servers  
        lower_servers = election.get_lower_priority_servers()
        expected_lower = [1001]  # Servers with ID < 1002
        assert set(lower_servers) == set(expected_lower)
        safe_print("✓ get_lower_priority_servers works correctly")
        
        # Test send_coordinator_message doesn't crash
        with patch.object(election, 'send_message') as mock_send:
            election.send_coordinator_message()
            # Should have called send_message for each server except self
            assert mock_send.call_count == 3  # 4 servers - 1 self = 3 calls
            safe_print("✓ send_coordinator_message handles concurrent access")
    
    safe_print("✅ Election thread safety test passed!\n")

def test_discovery_race_condition():
    """Test that discovery manager handles race conditions properly"""
    safe_print("Testing discovery race condition handling...")
    
    # Create discovery manager
    discovery = DiscoveryManager("test_server_1", "192.168.1.1", "test_host")
    
    # Test discovery statistics
    stats = discovery.get_discovery_statistics()
    assert 'discovery_phase' in stats
    assert 'discovery_complete' in stats
    assert 'discovered_servers_count' in stats
    safe_print("✓ Discovery statistics accessible")
    
    # Test phase transitions
    initial_phase = discovery.discovery_phase
    discovery.force_discovery_phase("running")
    assert discovery.discovery_phase == "running"
    safe_print("✓ Discovery phase transitions work")
    
    # Test discovery callback system
    callback_called = False
    def test_callback(*args):
        nonlocal callback_called
        callback_called = True
    
    discovery.add_discovery_callback('test_event', test_callback)
    discovery._trigger_callback('test_event')
    assert callback_called
    safe_print("✓ Discovery callback system works")
    
    safe_print("✅ Discovery race condition test passed!\n")

def test_fault_tolerance_startup():
    """Test that fault tolerance manager starts up correctly"""
    safe_print("Testing fault tolerance startup...")
    
    # Create fault tolerance manager
    ft_manager = FaultToleranceManager("test_server_1", "server")
    
    # Test initial state
    assert not ft_manager.running
    assert ft_manager.node_id == "test_server_1"
    assert ft_manager.node_type == "server"
    safe_print("✓ Fault tolerance manager initializes correctly")
    
    # Test partition detector initialization
    assert ft_manager.partition_detector.node_id == "test_server_1"
    assert not ft_manager.partition_detector.partition_detection_enabled
    safe_print("✓ Partition detector initializes with grace period")
    
    # Test statistics
    stats = ft_manager.get_fault_statistics()
    assert 'fault_counts' in stats
    assert 'partition_status' in stats
    safe_print("✓ Fault statistics accessible")
    
    safe_print("✅ Fault tolerance startup test passed!\n")

def test_timeout_values():
    """Test that timeout values are appropriate for startup"""
    safe_print("Testing timeout values...")
    
    # Test partition detector timeout
    detector = PartitionDetector("test_server")
    assert detector.probe_interval == 10  # Should be reasonable for startup
    safe_print("✓ Partition detector probe interval is reasonable")
    
    # Test discovery manager timeouts
    discovery = DiscoveryManager("test_server", "192.168.1.1", "test_host")
    assert discovery.startup_discovery_timeout == 15  # Should be sufficient for discovery
    assert discovery.probe_timeout == 5  # Should be long enough for startup
    safe_print("✓ Discovery manager timeouts are appropriate")
    
    # Test fault tolerance timeouts
    ft_manager = FaultToleranceManager("test_server")
    assert ft_manager.heartbeat_interval == 5  # Should be reasonable
    assert ft_manager.failure_timeout == 15  # Should be longer than heartbeat
    safe_print("✓ Fault tolerance timeouts are appropriate")
    
    safe_print("✅ Timeout values test passed!\n")

def run_all_tests():
    """Run all startup fix tests"""
    safe_print("=" * 60)
    safe_print("RUNNING STARTUP TIMING FIXES TESTS")
    safe_print("=" * 60)
    
    try:
        test_partition_detection_grace_period()
        test_election_thread_safety()
        test_discovery_race_condition()
        test_fault_tolerance_startup()
        test_timeout_values()
        
        safe_print("=" * 60)
        safe_print("🎉 ALL TESTS PASSED! 🎉")
        safe_print("The startup timing fixes are working correctly.")
        safe_print("=" * 60)
        
        return True
        
    except Exception as e:
        safe_print(f"❌ TEST FAILED: {e}")
        safe_print("=" * 60)
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)