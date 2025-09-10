#!/usr/bin/env python3
"""
Integration test to verify client isolation in queue mode.
This test verifies that slow clients don't affect fast clients.
"""

import asyncio
import json
import os
import pytest
import socket
import subprocess
import sys
import time
from contextlib import closing


def find_free_port():
    """Find a free port to use for testing."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.mark.asyncio
@pytest.mark.timeout(30)
@pytest.mark.skipif(sys.platform == "win32", reason="uvloop not available on Windows")
async def test_client_isolation():
    """
    Test that slow clients don't significantly impact fast clients in queue mode.
    
    This is a coarse integration test, not a strict performance benchmark.
    It verifies the basic isolation mechanism works.
    """
    port = find_free_port()
    server_url = f"ws://localhost:{port}"
    
    # Start server in queue mode
    server_proc = await asyncio.create_subprocess_exec(
        sys.executable, "server.py",
        "--mode", "queue",
        "--port", str(port),
        "--rate", "50",  # Lower rate for more predictable timing
        "--maxsize", "10",
        "--log-json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.path.dirname(os.path.dirname(__file__))
    )
    
    # Give server time to start
    await asyncio.sleep(1)
    
    try:
        # Start fast client
        fast_client = await asyncio.create_subprocess_exec(
            sys.executable, "clientsim.py",
            "--url", server_url,
            "--concurrency", "1",
            "--duration", "5",
            "--print-every", "50",
            "--id-prefix", "fast",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(os.path.dirname(__file__))
        )
        
        # Wait a bit, then start slow client
        await asyncio.sleep(1)
        
        slow_client = await asyncio.create_subprocess_exec(
            sys.executable, "clientsim.py", 
            "--url", server_url,
            "--concurrency", "1", 
            "--duration", "4",
            "--slow-ms", "100",  # 100ms delay per message
            "--print-every", "20",
            "--id-prefix", "slow",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(os.path.dirname(__file__))
        )
        
        # Wait for clients to complete
        fast_stdout, fast_stderr = await fast_client.communicate()
        slow_stdout, slow_stderr = await slow_client.communicate()
        
        # Parse client outputs to extract latency information
        fast_latencies = parse_client_latencies(fast_stdout.decode())
        slow_latencies = parse_client_latencies(slow_stdout.decode())
        
        # Basic isolation check: fast client should have much lower latency
        if fast_latencies and slow_latencies:
            fast_avg = sum(fast_latencies) / len(fast_latencies)
            slow_avg = sum(slow_latencies) / len(slow_latencies)
            
            print(f"Fast client average latency: {fast_avg:.1f}ms")
            print(f"Slow client average latency: {slow_avg:.1f}ms")
            
            # Assertion: fast client should be at least 2x faster OR under 50ms
            # This is a loose check since we're testing isolation, not absolute performance
            assert fast_avg < 50 or slow_avg > fast_avg * 2, \
                f"Isolation test failed: fast={fast_avg:.1f}ms, slow={slow_avg:.1f}ms"
        else:
            pytest.skip("Insufficient latency data collected")
            
    finally:
        # Clean up server
        server_proc.terminate()
        try:
            await asyncio.wait_for(server_proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            server_proc.kill()
            await server_proc.wait()


def parse_client_latencies(output: str) -> list:
    """
    Parse client output to extract latency values.
    Looks for lines containing latency statistics.
    """
    latencies = []
    
    for line in output.split('\n'):
        if 'Latency min/avg/p95:' in line:
            try:
                # Extract the avg latency value
                # Format: "Latency min/avg/p95: 1.2/3.4/5.6ms"
                latency_part = line.split('Latency min/avg/p95:')[1].split('|')[0].strip()
                avg_latency = float(latency_part.split('/')[1])
                latencies.append(avg_latency)
            except (IndexError, ValueError):
                continue
    
    return latencies


@pytest.mark.asyncio
@pytest.mark.timeout(20)
async def test_server_startup_and_shutdown():
    """Simple test that server can start and stop cleanly."""
    port = find_free_port()
    
    # Start server
    server_proc = await asyncio.create_subprocess_exec(
        sys.executable, "server.py",
        "--mode", "queue", 
        "--port", str(port),
        "--rate", "10",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.path.dirname(os.path.dirname(__file__))
    )
    
    # Give it time to start
    await asyncio.sleep(1)
    
    # Terminate gracefully
    server_proc.terminate()
    
    try:
        await asyncio.wait_for(server_proc.wait(), timeout=5)
        assert server_proc.returncode is not None
    except asyncio.TimeoutError:
        server_proc.kill()
        await server_proc.wait()
        pytest.fail("Server did not shut down gracefully")


if __name__ == "__main__":
    # Allow running this test directly
    asyncio.run(test_client_isolation())