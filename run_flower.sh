#!/bin/bash
# This script runs Celery Flower with the correct Redis broker configuration

# Check if CELERY_BROKER_URL environment variable is set
if [ -z "$CELERY_BROKER_URL" ]; then
    # If not set, try to extract it using Python
    echo "CELERY_BROKER_URL not set, attempting to extract from application settings..."
    BROKER_URL=$(python -c "from app.core.config import get_settings; print(get_settings().celery_broker_url)")
else
    BROKER_URL=$CELERY_BROKER_URL
fi

# Check if we have a broker URL
if [ -z "$BROKER_URL" ]; then
    echo "Error: Could not determine broker URL. Please set CELERY_BROKER_URL environment variable."
    exit 1
fi

# Run flower with the correct broker URL
echo "Starting Flower with broker: $BROKER_URL"
celery -A app.celery.worker.celery flower --broker=$BROKER_URL

# Exit with the status of the celery command
exit $?
