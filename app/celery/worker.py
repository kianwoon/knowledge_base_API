import asyncio
import os
from celery import Celery
from loguru import logger
from app.core.config import get_settings
from app.core.snowflake import generate_id
import importlib
import pkgutil


# Get configuration settings
settings = get_settings()

# Define broker URL and result backend from settings or environment variables
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', settings.celery_broker_url)
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', settings.celery_result_backend) 
 
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
    
# Build beat schedule from configuration
BEAT_SCHEDULE = {}
if settings.celery_beat_schedule_config:
    for job_name, job_config in settings.celery_beat_schedule_config.items():
        BEAT_SCHEDULE[job_name] = {
            'task': job_config.get('task'),
            'schedule': int(job_config.get('schedule', 10)),
            'args': job_config.get('args', ()),
        }
        logger.info(f"Added scheduled job: {job_name}")
else:
    logger.warning("No Celery beat schedule found in configuration")

# Task ID generator function
def generate_task_id():
    return str(generate_id())



# # Find all task modules in the app/tasks directory
# def discover_tasks():
#     task_modules = []
#     tasks_package = 'app.tasks'
    
#     try:
#         # Import the tasks package
#         tasks_pkg = importlib.import_module(tasks_package)
        
#         # Get the package path
#         pkg_path = os.path.dirname(tasks_pkg.__file__)
        
#         # Walk through all modules in the package
#         for _, name, is_pkg in pkgutil.iter_modules([pkg_path]):
#             # Add the module to the list (excluding subpackages)
#             if not is_pkg:
#                 task_modules.append(f"{tasks_package}.{name}")
#                 logger.info(f"Discovered task module: {tasks_package}.{name}")
    
#     except (ImportError, AttributeError) as e:
#         logger.warning(f"Could not discover task modules: {e}")
    
#     return task_modules

# # Get all task modules
# task_modules = discover_tasks


# Initialize Celery app with more robust connection settings
celery = Celery(
    'celery_analyzer_api',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['app.celery.tasks_email', 
             'app.celery.tasks_embedding_sharepoint', 
             'app.celery.tasks_embedding_mail', 
             'app.celery.tasks_embedding_aws_s3',
             'app.celery.tasks_embedding_azure',
             'app.celery'],
)

# Override the default task ID generator
celery.gen_task_id = generate_task_id

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
    task_queue_max_priority=10,
    task_default_priority=5,
)

if __name__ == '__main__':
    celery.start()