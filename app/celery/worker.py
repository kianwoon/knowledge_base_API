import asyncio
import os
from celery import Celery
from loguru import logger
from app.core.config import get_settings
from app.core.snowflake import generate_id

# Get configuration settings
settings = get_settings()

# Define broker URL and result backend from settings or environment variables
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', settings.celery_broker_url)
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', settings.celery_result_backend)
BEAT_SCHEDULE_INTERVAL = os.getenv('BEAT_SCHEDULE_INTERVAL', settings.celery_beat_schedule)

# Log the broker URL (without password if present)
def mask_password_in_url(url):
    if '@' in url and '://' in url:
        protocol_part = url.split('://')[0]
        rest = url.split('://')[1]
        if ':' in rest and '@' in rest:
            # There's a password
            user_pass = rest.split('@')[0]
            user = user_pass.split(':')[0]
            host_part = rest.split('@')[1]
            return f"{protocol_part}://{user}:****@{host_part}"
    return url

logger.info(f"Celery broker URL: {mask_password_in_url(CELERY_BROKER_URL)}")
logger.info(f"Celery result backend: {mask_password_in_url(CELERY_RESULT_BACKEND)}")

def get_or_create_event_loop():
    """Get the current event loop or create a new one if needed."""
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
    
# Fallback to hardcoded schedule for testing if needed

BEAT_SCHEDULE = {
    'check-pending-mail-jobs': {
        'task': 'mail_embedding.get_pending_jobs',
        'schedule': BEAT_SCHEDULE_INTERVAL,  # Default every 10 seconds
        'args': (),
    } ,
        'check-pending-sharepoint-jobs': {
        'task': 'sharepoint_embedding.get_pending_jobs',
        'schedule': BEAT_SCHEDULE_INTERVAL,  # Default every 10 seconds
        'args': (),
    },
    'check-pending-aws-s3-jobs': {
        'task': 'aws_s3_embedding.get_pending_jobs',
        'schedule': BEAT_SCHEDULE_INTERVAL,  # Default every 10 seconds
        'args': (),
    }

}

# BEAT_SCHEDULE = {
#         'check-pending-sharepoint-jobs': {
#         'task': 'sharepoint_embedding.get_pending_jobs',
#         'schedule': 15,  # Default every 10 seconds
#         'args': (),
#     } 
# }


# BEAT_SCHEDULE={}
# Task ID generator function
def generate_task_id():
    return str(generate_id())

# Initialize Celery app with more robust connection settings
celery = Celery(
    'celery_analyzer_api',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['app.celery.tasks_email', 'app.celery.tasks_embedding_sharepoint', 'app.celery.tasks_embedding_mail', 'app.celery.tasks_embedding_aws_s3', 'app.celery'],
)

# Override the default task ID generator
celery.gen_task_id = generate_task_id


# celery.conf.task_routes = {
#     'mail_embedding.get_pending_jobs': {'queue': 'pending_jobs'},
#     'mail_embedding.task_processing': {'queue': 'mail_embedding'},

#     'sharepoint_embedding.get_pending_jobs': {'queue': 'pending_jobs'},
#     'sharepoint_embedding.task_processing': {'queue': 'sharepoint_embedding'},

#     'tasks_email.process_subjects': {'queue': 'mail_subject'}, 
# }


# Configure Celery
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Singapore',
    enable_utc=False,
    beat_schedule=BEAT_SCHEDULE,
    # Broker connection retry settings
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_connection_timeout=5,
)

if __name__ == '__main__':
    celery.start()