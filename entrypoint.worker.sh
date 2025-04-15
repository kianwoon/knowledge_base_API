#!/bin/sh
exec celery -A app.celery.worker.celery worker --loglevel=info --autoscale=${ENV_CELERY_CONCURRENCY:-2},1 --max-tasks-per-child=${ENV_CELERY_MAX_TASKS_PER_CHILD:-100}