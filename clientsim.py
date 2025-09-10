#!/usr/bin/env python3
"""
WebSocket client simulator for load and latency testing.
"""

import argparse
import asyncio
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import List, Optional

import websockets


@dataclass
class ClientStats:
    """Per-client statistics tracking."""
    count: int = 0
    latencies: List[float] = field(default_factory=list)
    last_seq: int = 0
    drops_inferred: int = 0
    connect_time: Optional[float] = None
    last_message_time: Optional[float] = None


class ClientSimulator:
    """WebSocket client simulator."""
    
    def __init__(self, args):
        self.args = args
        self.stats: List[ClientStats] = []
        self.start_time = time.time()
        
    def create_client_stats(self) -> ClientStats:
        """Create new client statistics tracker."""
        stats = ClientStats()
        self.stats.append(stats)
        return stats
    
    async def client_worker(self, client_id: int, stats: ClientStats):
        """Individual client worker coroutine."""
        url = self.args.url
        client_name = f"{self.args.id_prefix}-{client_id}"
        
        backoff = 1
        max_backoff = 30
        
        while time.time() - self.start_time < self.args.duration:
            try:
                async with websockets.connect(url) as websocket:
                    stats.connect_time = time.time()
                    print(f"[{client_name}] Connected to {url}")
                    backoff = 1  # Reset backoff on successful connection
                    
                    async for message in websocket:
                        await self.process_message(message, stats, client_name)
                        
                        # Simulate slow processing
                        if self.args.slow_ms > 0:
                            delay = self.args.slow_ms / 1000.0
                            if self.args.jitter_ms > 0:
                                jitter = (random.random() - 0.5) * 2 * (self.args.jitter_ms / 1000.0)
                                delay += jitter
                            await asyncio.sleep(max(0, delay))
                        
                        # Check if duration expired
                        if time.time() - self.start_time >= self.args.duration:
                            break
                            
            except websockets.exceptions.ConnectionClosed:
                print(f"[{client_name}] Connection closed")
            except Exception as e:
                print(f"[{client_name}] Error: {e}")
            
            # Exponential backoff for reconnection
            if time.time() - self.start_time < self.args.duration:
                print(f"[{client_name}] Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
    
    async def process_message(self, message: str, stats: ClientStats, client_name: str):
        """Process received message and update statistics."""
        try:
            data = json.loads(message)
            recv_time = time.time()
            
            # Calculate end-to-end latency
            if "ts_send" in data:
                e2e_latency = (recv_time - data["ts_send"]) * 1000  # ms
                stats.latencies.append(e2e_latency)
            
            # Detect dropped messages
            seq = data.get("seq", 0)
            if stats.last_seq > 0 and seq > stats.last_seq + 1:
                drops = seq - stats.last_seq - 1
                stats.drops_inferred += drops
            
            stats.last_seq = seq
            stats.count += 1
            stats.last_message_time = recv_time
            
            # Print periodic statistics
            if stats.count % self.args.print_every == 0:
                self.print_client_stats(stats, client_name)
                
        except json.JSONDecodeError:
            print(f"[{client_name}] Invalid JSON message")
        except Exception as e:
            print(f"[{client_name}] Message processing error: {e}")
    
    def print_client_stats(self, stats: ClientStats, client_name: str):
        """Print current statistics for a client."""
        if not stats.latencies:
            return
        
        min_lat = min(stats.latencies)
        avg_lat = statistics.mean(stats.latencies)
        p95_lat = statistics.quantiles(stats.latencies, n=20)[18] if len(stats.latencies) >= 20 else max(stats.latencies)
        
        runtime = time.time() - self.start_time
        rate = stats.count / runtime if runtime > 0 else 0
        
        print(f"[{client_name}] Count: {stats.count:6d} | "
              f"Rate: {rate:6.1f}/s | "
              f"Latency min/avg/p95: {min_lat:6.1f}/{avg_lat:6.1f}/{p95_lat:6.1f}ms | "
              f"Drops: {stats.drops_inferred}")
    
    def print_final_summary(self):
        """Print final summary statistics."""
        print("\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        
        total_messages = sum(s.count for s in self.stats)
        total_drops = sum(s.drops_inferred for s in self.stats)
        runtime = time.time() - self.start_time
        
        print(f"Total Runtime: {runtime:.1f}s")
        print(f"Total Messages: {total_messages}")
        print(f"Total Drops: {total_drops}")
        print(f"Overall Rate: {total_messages/runtime:.1f} msg/s")
        print()
        
        # Per-client summary
        print(f"{'Client':<15} {'Messages':<10} {'Rate/s':<8} {'Min':<8} {'Avg':<8} {'P95':<8} {'Drops':<8}")
        print("-" * 80)
        
        for i, stats in enumerate(self.stats):
            client_name = f"{self.args.id_prefix}-{i}"
            
            if stats.latencies:
                min_lat = min(stats.latencies)
                avg_lat = statistics.mean(stats.latencies)
                p95_lat = statistics.quantiles(stats.latencies, n=20)[18] if len(stats.latencies) >= 20 else max(stats.latencies)
            else:
                min_lat = avg_lat = p95_lat = 0
            
            rate = stats.count / runtime if runtime > 0 else 0
            
            print(f"{client_name:<15} {stats.count:<10} {rate:<8.1f} "
                  f"{min_lat:<8.1f} {avg_lat:<8.1f} {p95_lat:<8.1f} {stats.drops_inferred:<8}")
    
    async def run(self):
        """Run the client simulation."""
        print(f"Starting {self.args.concurrency} clients for {self.args.duration}s")
        print(f"Target: {self.args.url}")
        if self.args.slow_ms > 0:
            print(f"Slow mode: {self.args.slow_ms}ms delay per message")
        if self.args.jitter_ms > 0:
            print(f"Jitter: ±{self.args.jitter_ms}ms")
        print()
        
        # Create client tasks
        tasks = []
        for i in range(self.args.concurrency):
            stats = self.create_client_stats()
            task = asyncio.create_task(self.client_worker(i, stats))
            tasks.append(task)
        
        # Wait for all clients to complete
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.print_final_summary()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="WebSocket client simulator")
    
    parser.add_argument("--url", default="ws://localhost:8765",
                       help="WebSocket server URL")
    parser.add_argument("--concurrency", type=int, default=1,
                       help="Number of concurrent connections")
    parser.add_argument("--slow-ms", type=int, default=0,
                       help="Processing delay per message (ms)")
    parser.add_argument("--jitter-ms", type=int, default=0,
                       help="Random latency jitter (ms)")
    parser.add_argument("--duration", type=int, default=30,
                       help="Test duration (seconds)")
    parser.add_argument("--print-every", type=int, default=100,
                       help="Print stats every N messages")
    parser.add_argument("--id-prefix", default="cli",
                       help="Client ID prefix")
    
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    simulator = ClientSimulator(args)
    await simulator.run()


if __name__ == "__main__":
    asyncio.run(main())