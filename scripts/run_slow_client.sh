#!/bin/sh

# Run one slow client with processing delay

cd "$(dirname "$0")/.."

URL=${1:-ws://localhost:8765}

echo "Starting 1 slow client for 30 seconds..."
echo "This client processes messages with 200ms delay."
echo "Target: $URL"
echo ""

python3 clientsim.py --url "$URL" --concurrency 1 --slow-ms 200 --duration 30 --id-prefix cli-slow

echo ""
echo "Slow client completed."