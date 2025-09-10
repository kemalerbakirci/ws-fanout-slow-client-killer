#!/bin/sh

# WebSocket Fanout Slow Client Killer - Naive Mode
# Demonstrates backpressure problem where slow clients stall entire broadcast

cd "$(dirname "$0")/.."

echo "=================================="
echo "  NAIVE MODE SERVER STARTING"
echo "=================================="
echo "This mode will stall ALL clients when one client is slow!"
echo ""
echo "To test the stall behavior:"
echo "  Terminal 2: make fast-clients"
echo "  Terminal 3: make slow-client"
echo ""
echo "Watch how latency spikes for ALL clients when slow client connects."
echo "=================================="
echo ""

exec python3 server.py --mode naive --rate 100 --payload-bytes 64