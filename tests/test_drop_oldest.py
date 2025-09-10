#!/usr/bin/env python3
"""
Test the drop-oldest queue functionality.
"""

import asyncio
import pytest
from dataclasses import dataclass

# Import the function we want to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import BroadcastServer, ClientState


@dataclass
class MockArgs:
    """Mock arguments for BroadcastServer."""
    mode = "queue"
    maxsize = 2
    drop_limit = 50
    full_timeout = 5
    log_json = True


@pytest.mark.asyncio
async def test_enqueue_with_drop_oldest_when_full():
    """Test that enqueue_with_drop_oldest drops oldest item when queue is full."""
    # Setup
    args = MockArgs()
    server = BroadcastServer(args)
    queue = asyncio.Queue(maxsize=2)
    state = ClientState()
    
    # Fill the queue
    queue.put_nowait("message1")
    queue.put_nowait("message2")
    
    # Queue should be full
    assert queue.qsize() == 2
    assert state.drops_total == 0
    
    # Try to add a third message - should drop oldest
    dropped = server.enqueue_with_drop_oldest(queue, "message3", state)
    
    # Verify drop occurred
    assert dropped == True
    assert queue.qsize() == 2  # Queue size unchanged
    assert state.drops_total == 1  # Drop counter increased
    
    # Verify the queue contains message2 and message3 (message1 was dropped)
    item1 = queue.get_nowait()
    item2 = queue.get_nowait()
    assert item1 == "message2"
    assert item2 == "message3"


@pytest.mark.asyncio
async def test_enqueue_with_drop_oldest_when_not_full():
    """Test that enqueue_with_drop_oldest works normally when queue not full."""
    # Setup
    args = MockArgs()
    server = BroadcastServer(args)
    queue = asyncio.Queue(maxsize=2)
    state = ClientState()
    
    # Add one message to partially fill queue
    queue.put_nowait("message1")
    
    assert queue.qsize() == 1
    assert state.drops_total == 0
    
    # Add second message - should not drop
    dropped = server.enqueue_with_drop_oldest(queue, "message2", state)
    
    # Verify no drop occurred
    assert dropped == False
    assert queue.qsize() == 2
    assert state.drops_total == 0
    
    # Verify both messages are in queue
    item1 = queue.get_nowait()
    item2 = queue.get_nowait()
    assert item1 == "message1"
    assert item2 == "message2"


@pytest.mark.asyncio
async def test_enqueue_tracks_drop_times():
    """Test that drop times are tracked for the drop window."""
    args = MockArgs()
    server = BroadcastServer(args)
    queue = asyncio.Queue(maxsize=1)
    state = ClientState()
    
    # Fill queue
    queue.put_nowait("message1")
    
    # Drop several messages
    server.enqueue_with_drop_oldest(queue, "message2", state)
    server.enqueue_with_drop_oldest(queue, "message3", state)
    
    # Verify drops are tracked
    assert state.drops_total == 2
    assert len(state.last_drop_window) == 2
    
    # All drop times should be recent
    import time
    now = time.time()
    for drop_time in state.last_drop_window:
        assert drop_time <= now
        assert drop_time > now - 1  # Within last second


@pytest.mark.asyncio 
async def test_queue_full_timeout_tracking():
    """Test that queue full timeout is tracked properly."""
    args = MockArgs()
    server = BroadcastServer(args)
    queue = asyncio.Queue(maxsize=1)
    state = ClientState()
    
    # Fill queue
    queue.put_nowait("message1")
    
    # Should track when queue becomes full
    assert state.queue_full_since is None
    
    # Drop a message - should start tracking full time
    server.enqueue_with_drop_oldest(queue, "message2", state)
    assert state.queue_full_since is not None
    
    # Empty the queue by getting the message
    queue.get_nowait()
    
    # Add message to non-full queue - should reset full time
    server.enqueue_with_drop_oldest(queue, "message3", state)
    assert state.queue_full_since is None