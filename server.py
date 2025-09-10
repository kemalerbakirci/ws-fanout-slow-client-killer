#!/usr/bin/env python3
"""
WebSocket broadcast server with naive and queue modes.
Demonstrates backpressure isolation using per-client bounded queues.
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import signal
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import websockets

try:
    import uvloop
    if sys.platform != "win32":
        uvloop.install()
except ImportError:
    pass


@dataclass
class ClientState:
    """Per-client state tracking."""
    queue: Optional[asyncio.Queue] = None
    drops_total: int = 0
    send_times: deque = field(default_factory=lambda: deque(maxlen=100))
    last_drop_window: deque = field(default_factory=lambda: deque(maxlen=100))
    queue_full_since: Optional[float] = None
    relay_task: Optional[asyncio.Task] = None


class BroadcastServer:
    """WebSocket broadcast server with naive and queue modes."""
    
    def __init__(self, args):
        self.args = args
        self.clients: Dict[websockets.WebSocketServerProtocol, ClientState] = {}
        self.publisher_task: Optional[asyncio.Task] = None
        self.metrics_task: Optional[asyncio.Task] = None
        self.server = None
        self.seq = 0
        self.total_disconnects = 0
        self.e2e_latencies: deque = deque(maxlen=1000)
        self._last_log_time = 0  # Initialize log time tracking
        
        # Setup logging
        if args.log_json:
            logging.basicConfig(
                level=logging.INFO,
                format='%(message)s',
                handlers=[logging.StreamHandler()]
            )
        else:
            try:
                from rich.console import Console
                from rich.logging import RichHandler
                console = Console()
                logging.basicConfig(
                    level=logging.INFO,
                    format="%(message)s",
                    handlers=[RichHandler(console=console, rich_tracebacks=True)]
                )
            except ImportError:
                # Fallback to standard logging if rich is not available
                logging.basicConfig(
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s'
                )
        
        self.logger = logging.getLogger(__name__)

    async def register_client(self, websocket: websockets.WebSocketServerProtocol):
        """Register a new client connection."""
        state = ClientState()
        
        if self.args.mode == "queue":
            state.queue = asyncio.Queue(maxsize=self.args.maxsize)
            state.relay_task = asyncio.create_task(
                self.client_relay(websocket, state)
            )
        
        self.clients[websocket] = state
        self.logger.info(f"Client connected. Total: {len(self.clients)}")

    async def unregister_client(self, websocket: websockets.WebSocketServerProtocol):
        """Unregister a client connection."""
        if websocket in self.clients:
            state = self.clients[websocket]
            if state.relay_task:
                state.relay_task.cancel()
                try:
                    await state.relay_task
                except asyncio.CancelledError:
                    pass
            
            del self.clients[websocket]
            self.total_disconnects += 1
            self.logger.info(f"Client disconnected. Total: {len(self.clients)}")

    def enqueue_with_drop_oldest(self, queue: asyncio.Queue, item: Any, state: ClientState) -> bool:
        """
        Enqueue item, dropping oldest if queue is full.
        Returns True if item was dropped.
        """
        try:
            queue.put_nowait(item)
            if state.queue_full_since is not None:
                state.queue_full_since = None
            return False
        except asyncio.QueueFull:
            # Drop oldest message
            try:
                queue.get_nowait()
                queue.put_nowait(item)
                state.drops_total += 1
                state.last_drop_window.append(time.time())
                
                # Track queue full duration
                if state.queue_full_since is None:
                    state.queue_full_since = time.time()
                
                return True
            except asyncio.QueueEmpty:
                # Queue became empty between checks, try again
                try:
                    queue.put_nowait(item)
                    return False
                except asyncio.QueueFull:
                    return True

    async def client_relay(self, websocket: websockets.WebSocketServerProtocol, state: ClientState):
        """Relay messages from queue to client."""
        try:
            while True:
                message = await state.queue.get()
                start_time = time.time()
                
                try:
                    await websocket.send(message)
                    send_time = (time.time() - start_time) * 1000
                    state.send_times.append(send_time)
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    self.logger.error(f"Send error: {e}")
                    break
                
                state.queue.task_done()
        except asyncio.CancelledError:
            pass

    async def should_disconnect_client(self, state: ClientState) -> bool:
        """Check if client should be auto-disconnected."""
        now = time.time()
        
        # Check drops in last 10 seconds
        while state.last_drop_window and state.last_drop_window[0] < now - 10:
            state.last_drop_window.popleft()
        
        if len(state.last_drop_window) > self.args.drop_limit:
            return True
        
        # Check queue full timeout
        if (state.queue_full_since and 
            now - state.queue_full_since > self.args.full_timeout):
            return True
        
        return False

    async def broadcast_naive(self, message: str):
        """Naive broadcast - sequential sends."""
        if not self.clients:
            return
        
        disconnected = []
        for websocket in self.clients:
            try:
                await websocket.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.append(websocket)
            except Exception as e:
                self.logger.error(f"Broadcast error: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for websocket in disconnected:
            await self.unregister_client(websocket)

    async def broadcast_queue(self, message: str):
        """Queue-based broadcast - concurrent sends via queues."""
        if not self.clients:
            return
        
        disconnected = []
        for websocket, state in list(self.clients.items()):
            try:
                dropped = self.enqueue_with_drop_oldest(state.queue, message, state)
                
                if await self.should_disconnect_client(state):
                    self.logger.info(f"Auto-disconnecting slow client (drops: {state.drops_total})")
                    disconnected.append(websocket)
                    
            except Exception as e:
                self.logger.error(f"Queue error: {e}")
                disconnected.append(websocket)
        
        # Clean up clients marked for disconnection
        for websocket in disconnected:
            try:
                await websocket.close()
            except:
                pass
            await self.unregister_client(websocket)

    async def publisher(self):
        """Publish synthetic messages at specified rate."""
        interval = 1.0 / self.args.rate
        payload = base64.b64encode(os.urandom(self.args.payload_bytes)).decode()
        
        while True:
            self.seq += 1
            message = json.dumps({
                "seq": self.seq,
                "ts_send": time.time(),
                "payload_b64": payload
            })
            
            if self.args.mode == "naive":
                await self.broadcast_naive(message)
            else:
                await self.broadcast_queue(message)
            
            await asyncio.sleep(interval)

    async def log_metrics(self):
        """Log metrics every 5 seconds (less verbose)."""
        while True:
            await asyncio.sleep(5)  # Log every 5 seconds instead of 1
            
            # Calculate percentiles
            latencies = list(self.e2e_latencies)
            if latencies:
                latencies.sort()
                p50 = latencies[len(latencies) // 2] if latencies else 0
                p95_idx = int(len(latencies) * 0.95)
                p95 = latencies[p95_idx] if latencies else 0
            else:
                p50 = p95 = 0
            
            if self.args.log_json:
                metrics = {
                    "type": "summary",
                    "clients": len(self.clients),
                    "pub_rate": self.args.rate,
                    "e2e_latency": {"p50": round(p50, 1), "p95": round(p95, 1)},
                    "disconnects_total": self.total_disconnects
                }
                self.logger.info(json.dumps(metrics))
                
                # Per-client metrics
                for i, (websocket, state) in enumerate(self.clients.items()):
                    client_metrics = {
                        "type": "client",
                        "client_id": i,
                        "queue_len": state.queue.qsize() if state.queue else 0,
                        "drops_total": state.drops_total,
                        "send_latency_ms": round(
                            sum(state.send_times) / len(state.send_times), 1
                        ) if state.send_times else 0
                    }
                    self.logger.info(json.dumps(client_metrics))
            else:
                # Only log if there are clients or if it's been a while
                if len(self.clients) > 0 or hasattr(self, '_last_log_time') and time.time() - self._last_log_time > 30:
                    self.logger.info(
                        f"Clients: {len(self.clients)} | "
                        f"Rate: {self.args.rate}/s | "
                        f"E2E p50/p95: {p50:.1f}/{p95:.1f}ms | "
                        f"Disconnects: {self.total_disconnects}"
                    )
                    self._last_log_time = time.time()

    async def handle_client(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """Handle new client connection."""
        await self.register_client(websocket)
        try:
            async for message in websocket:
                # Handle client ACKs for latency calculation
                try:
                    data = json.loads(message)
                    if "ack_ts" in data:
                        e2e_latency = (time.time() - data["ack_ts"]) * 1000
                        self.e2e_latencies.append(e2e_latency)
                except (json.JSONDecodeError, KeyError):
                    pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(websocket)

    async def stop(self):
        """Stop the server gracefully."""
        self.logger.info("Shutting down server...")
        
        # Cancel tasks
        if self.publisher_task:
            self.publisher_task.cancel()
        if self.metrics_task:
            self.metrics_task.cancel()
        
        # Close all client connections
        if self.clients:
            await asyncio.gather(
                *[ws.close() for ws in self.clients.keys()],
                return_exceptions=True
            )
        
        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="WebSocket broadcast server")
    
    parser.add_argument("--mode", choices=["naive", "queue"], default="queue",
                       help="Broadcast mode")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=8765, help="Listen port")
    parser.add_argument("--rate", type=float, default=100, help="Messages per second")
    parser.add_argument("--payload-bytes", type=int, default=64, help="Payload size")
    parser.add_argument("--maxsize", type=int, default=100, help="Queue size per client")
    parser.add_argument("--drop-limit", type=int, default=50, help="Auto-disconnect threshold")
    parser.add_argument("--full-timeout", type=float, default=5, help="Queue full timeout")
    parser.add_argument("--ping-interval", type=float, default=20, help="Ping interval")
    parser.add_argument("--ping-timeout", type=float, default=20, help="Ping timeout")
    parser.add_argument("--log-json", action="store_true", help="JSON log format")
    parser.add_argument("--config", help="YAML config file")
    
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    
    server = BroadcastServer(args)
    
    # Create a future to signal shutdown
    shutdown_event = asyncio.Event()
    
    # Setup signal handlers
    def signal_handler():
        shutdown_event.set()
    
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        # Start server components
        server.server = await websockets.serve(
            server.handle_client,
            args.host,
            args.port,
            ping_interval=args.ping_interval,
            ping_timeout=args.ping_timeout
        )
        
        server.publisher_task = asyncio.create_task(server.publisher())
        server.metrics_task = asyncio.create_task(server.log_metrics())
        
        server.logger.info(f"Server started on {args.host}:{args.port} in {args.mode} mode")
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
    except KeyboardInterrupt:
        pass
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())