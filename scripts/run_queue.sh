#!/bin/sh

# WebSocket Fanout Slow Client Killer - Queue Mode
# Demonstrates backpressure isolation using per-client bounded queues

cd "$(dirname "$0")/.."

echo "=================================="
echo "  QUEUE MODE SERVER STARTING"
echo "=================================="
echo "This mode isolates slow clients with bounded queues!"
echo ""
echo "Features:"
echo "  - Per-client queues (max 100 msgs)"
echo "  - Drop oldest when queue full"
echo "  - Auto-disconnect after 50 drops in 10s"
echo "  - Auto-disconnect if queue full > 5s"
echo ""
echo "To test isolation:"
echo "  Terminal 2: make fast-clients"
echo "  Terminal 3: make slow-client"
echo ""
echo "Fast clients will remain unaffected by slow client!"
echo "=================================="
echo ""

exec python3 server.py --mode queue --rate 100 --payload-bytes 64 --maxsize 100 --drop-limit 50 --full-timeout 5