#!/bin/bash
set -e

echo "Starting Mail Analyzer services..."

# Function to check if a process is still running
is_running() {
  ps -p $1 > /dev/null 2>&1
  return $?
}

# Function to start worker process
start_worker() {
  echo "Starting worker process..."
  python run_worker.py 2>&1 | sed 's/^/[WORKER] /' &
  echo $!
}

# Start the worker process
WORKER_PID=$(start_worker)
echo "Worker started with PID: $WORKER_PID"

# Start the API process (this is our main service)
echo "Starting API process..."
python run_api.py 2>&1 | sed 's/^/[API] /' &
API_PID=$!
echo "API started with PID: $API_PID"

# Handle termination signals
trap 'echo "Received termination signal. Shutting down all services..."; kill -TERM $WORKER_PID $API_PID 2>/dev/null || true; wait $WORKER_PID 2>/dev/null || true; wait $API_PID 2>/dev/null || true; echo "All processes terminated."; exit 0' TERM INT

echo "All services started. API PID: $API_PID, Worker PID: $WORKER_PID"

# Main service loop - keep running as long as API is alive
while is_running $API_PID; do
  # Check if worker is running, restart if needed
  if ! is_running $WORKER_PID; then
    # Worker exited, check its status
    if wait $WORKER_PID 2>/dev/null; then
      echo "Worker process exited normally. Restarting..."
      WORKER_PID=$(start_worker)
      echo "Worker restarted with PID: $WORKER_PID"
    else
      EXIT_STATUS=$?
      echo "Worker process exited with error status $EXIT_STATUS. Will restart in 10 seconds..."
      sleep 10
      WORKER_PID=$(start_worker)
      echo "Worker restarted with PID: $WORKER_PID"
    fi
  fi
  
  # Sleep to avoid high CPU usage
  sleep 2
done

# If we get here, the API process has exited
if wait $API_PID; then
  echo "API process exited normally. Shutting down all services..."
else
  EXIT_STATUS=$?
  echo "API process exited with error status $EXIT_STATUS. Shutting down all services..."
fi

# Kill the worker process if it's still running
if is_running $WORKER_PID; then
  kill -TERM $WORKER_PID 2>/dev/null || true
  wait $WORKER_PID 2>/dev/null || true
fi

echo "All processes have been terminated."
exit 0
