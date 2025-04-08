#!/bin/bash

# Directory for logs
LOGDIR="/app/logs"
mkdir -p $LOGDIR

# Function to start a process and monitor it
start_and_monitor() {
    local name="$1"
    local cmd="$2"
    local logfile="$LOGDIR/${name}.log"
    
    echo "Starting $name..."
    
    # Run the command, redirect output to both log file and stdout
    while true; do
        echo "[$(date)] Starting/Restarting $name" | tee -a "$logfile"
        $cmd 2>&1 | tee -a "$logfile" &
        pid=$!
        
        # Store the PID so we can kill it on shutdown
        echo $pid > "/tmp/${name}.pid"
        
        # Wait for the process to end
        wait $pid
        
        # If we get here, the process has ended
        echo "[$(date)] $name stopped with exit code $?. Restarting in 5 seconds..." | tee -a "$logfile"
        sleep 5
    done
}

# Function to handle termination signals
cleanup() {
    echo "Stopping all services..."
    
    # Kill all background processes
    if [ -f "/tmp/worker_qdrant.pid" ]; then
        kill -TERM $(cat "/tmp/worker_qdrant.pid") 2>/dev/null || true
    fi
    
    if [ -f "/tmp/worker_redis.pid" ]; then
        kill -TERM $(cat "/tmp/worker_redis.pid") 2>/dev/null || true
    fi
    
    if [ -f "/tmp/api.pid" ]; then
        kill -TERM $(cat "/tmp/api.pid") 2>/dev/null || true
    fi
    
    # Kill any remaining processes in this process group
    kill -TERM 0 2>/dev/null || true
    
    exit 0
}

# Set up signal handling
trap cleanup SIGINT SIGTERM

# Start each service in the background with monitoring
start_and_monitor "worker_qdrant" "python run_worker_qdrant.py" &
start_and_monitor "worker_redis" "python run_worker_redis.py" &
start_and_monitor "api" "python run_api.py" &

# Keep the script running
echo "All services started. Press Ctrl+C to stop."
wait
