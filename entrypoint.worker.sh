#!/bin/sh
exec celery -A app.celery.worker.celery worker --pool gevent --loglevel=info --autoscale=${ENV_CELERY_CONCURRENCY:-4},2 --max-tasks-per-child=${ENV_CELERY_MAX_TASKS_PER_CHILD:-100}