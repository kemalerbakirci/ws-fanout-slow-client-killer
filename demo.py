#!/usr/bin/env python3
"""
Simple demo script to show the ws-fanout-slow-client-killer working.
"""

import asyncio
import subprocess
import sys
import time
import signal
import os

async def demo():
    """Run a simple demo showing the difference between naive and queue modes."""
    
    python_path = "/Users/kemalerbakirci/Desktop/6-Months-Development/IoT/Projects/ws-fanout-slow-client-killer/.venv/bin/python"
    
    print("🚀 WebSocket Fanout Slow Client Killer Demo")
    print("=" * 50)
    
    # Test 1: Queue mode demo
    print("\n📊 Testing QUEUE MODE (with isolation)")
    print("-" * 30)
    
    # Start server in queue mode
    server_proc = await asyncio.create_subprocess_exec(
        python_path, "server.py",
        "--mode", "queue",
        "--rate", "50",
        "--port", "8765",
        "--log-json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Wait for server to start
    await asyncio.sleep(1)
    print("✅ Server started in queue mode")
    
    try:
        # Start fast client
        fast_client = await asyncio.create_subprocess_exec(
            python_path, "clientsim.py",
            "--url", "ws://localhost:8765",
            "--duration", "5",
            "--id-prefix", "fast",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await asyncio.sleep(1)
        print("✅ Fast client connected")
        
        # Start slow client
        slow_client = await asyncio.create_subprocess_exec(
            python_path, "clientsim.py",
            "--url", "ws://localhost:8765", 
            "--duration", "4",
            "--slow-ms", "100",
            "--id-prefix", "slow",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        print("✅ Slow client connected (100ms delay per message)")
        print("⏳ Running test for 5 seconds...")
        
        # Wait for clients to finish
        fast_stdout, _ = await fast_client.communicate()
        slow_stdout, _ = await slow_client.communicate()
        
        # Parse and display results
        print("\n📈 RESULTS:")
        print("Fast client output:")
        for line in fast_stdout.decode().split('\n')[-10:]:
            if line.strip() and ('Rate:' in line or 'FINAL' in line or 'fast' in line):
                print(f"  {line}")
        
        print("\nSlow client output:")
        for line in slow_stdout.decode().split('\n')[-10:]:
            if line.strip() and ('Rate:' in line or 'FINAL' in line or 'slow' in line):
                print(f"  {line}")
        
    finally:
        # Clean up
        print("\n🧹 Cleaning up...")
        server_proc.terminate()
        try:
            await asyncio.wait_for(server_proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            server_proc.kill()
        
    print("\n✅ Demo completed!")
    print("\n💡 In queue mode, the fast client should maintain low latency")
    print("   even when the slow client is processing messages slowly.")
    print("\n🔗 Try running the full demo with: make demo-queue")

if __name__ == "__main__":
    try:
        asyncio.run(demo())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        sys.exit(1)
