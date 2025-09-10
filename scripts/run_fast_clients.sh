#!/bin/sh

# Run 3 fast clients concurrently

cd "$(dirname "$0")/.."

echo "Starting 3 fast clients for 30 seconds..."
echo "These clients should maintain low, consistent latency."
echo ""

# Start clients in background
python3 clientsim.py --url ws://localhost:8765 --concurrency 1 --duration 30 --id-prefix cli-fast-0 &
python3 clientsim.py --url ws://localhost:8765 --concurrency 1 --duration 30 --id-prefix cli-fast-1 &
python3 clientsim.py --url ws://localhost:8765 --concurrency 1 --duration 30 --id-prefix cli-fast-2 &

# Wait for all background jobs to complete
wait

echo ""
echo "All fast clients completed."