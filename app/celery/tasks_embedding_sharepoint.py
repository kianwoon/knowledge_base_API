
from celery import shared_task
from loguru import logger
 
from app.worker.processors_file_sharepoint import EmbeddingSharepointProcessor as Processor
from app.celery.worker import get_or_create_event_loop

from app.models.task_config import TaskConfig

task = TaskConfig("sharepoint")
 
 
@shared_task(name=task.pending_task_name, queue=task.queue_name)
def get_pending_jobs():
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """
    logger.info("Check pending jobs.")
    
    processor = Processor(source_repository=task.source, job_type=task.job_type, task_name=task.task_name)
 
    loop = get_or_create_event_loop()
    results = loop.run_until_complete(processor.schedule_task())
    

    logger.info("Pending jobs retrieved: " + str(results))
    return results


@shared_task(name=task.task_name)
def process_embedding(job_data: str):
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """ 

    logger.info("Processing embedding task " + job_data)
 
    processor = Processor(source_repository=task.source, job_type=task.job_type)
    
    loop = get_or_create_event_loop()
    loop.run_until_complete(processor.do_embedding(job_data)) 
    return ["Finished"] 