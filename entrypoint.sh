#!/bin/bash
set -e

echo "Starting Mail Analyzer services..."

# Start the worker process in background and redirect logs
echo "Starting worker process..."
python run_worker.py 2>&1 | sed 's/^/[WORKER] /' &
WORKER_PID=$!

# Start the API process in background and redirect logs
echo "Starting API process..."
python run_api.py 2>&1 | sed 's/^/[API] /' &
API_PID=$!

# Handle termination signals
trap 'kill -TERM $WORKER_PID $API_PID; wait $WORKER_PID; wait $API_PID; echo "All processes terminated."; exit 0' TERM INT

echo "All services started. API PID: $API_PID, Worker PID: $WORKER_PID"

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
EXIT_STATUS=$?
echo "A process exited with status $EXIT_STATUS. Shutting down all services..."

# Kill all remaining processes
kill -TERM $WORKER_PID $API_PID 2>/dev/null || true
wait

exit $EXIT_STATUS
