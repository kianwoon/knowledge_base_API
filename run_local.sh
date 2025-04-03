#!/bin/bash
# Script to run the Mail Analysis API locally

# Check if config/settings.yaml file exists
if [ ! -f config/settings.yaml ]; then
    echo "Error: config/settings.yaml file not found. Please create one based on config/settings.example.yaml."
    exit 1
fi

# Source .env file
source .env

# # Check if Redis is running
# redis-cli ping > /dev/null 2>&1
# if [ $? -ne 0 ]; then
#     echo "Error: Redis is not running. Please start Redis first."
#     exit 1
# fi

# Check if OpenAI API key is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY is not set in .env file."
    exit 1
fi

# Check if encryption key is set
if [ -z "$ENCRYPTION_KEY" ]; then
    echo "Error: ENCRYPTION_KEY is not set in .env file."
    exit 1
fi

# Start API server in background
echo "Starting API server..."
python run_api.py &
API_PID=$!

# Start worker in background
echo "Starting worker..."
python run_worker.py &
WORKER_PID=$!

# Function to handle exit
function cleanup {
    echo "Stopping API server and worker..."
    kill $API_PID
    kill $WORKER_PID
    echo "Done."
}

# Register cleanup function
trap cleanup EXIT

# Wait for user input
echo "Press Ctrl+C to stop the application."
wait
