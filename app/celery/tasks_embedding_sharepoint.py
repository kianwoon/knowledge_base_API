
from celery import shared_task
from loguru import logger
 
from app.worker.processors_file_sharepoint import EmbeddingSharepointProcessor as Processor
from app.celery.worker import get_or_create_event_loop
 

@shared_task(name="sharepoint_embedding.get_pending_jobs")
def get_pending_jobs():
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """
    logger.info("Check pending jobs.")
    
    processor = Processor(source_repository="_sharepoint_knowledge", job_type="sharepoint", task_name="sharepoint_embedding.task_processing")
 
    loop = get_or_create_event_loop()
    results = loop.run_until_complete(processor.schedule_task())
    

    logger.info("Pending jobs retrieved: " + str(results))
    return results


@shared_task(name="sharepoint_embedding.task_processing")
def process_embedding(job_data: str):
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """ 

    logger.info("Processing embedding task " + job_data)
 
    processor = Processor(source_repository="_sharepoint_knowledge", job_type="sharepoint")
    
    loop = get_or_create_event_loop()
    loop.run_until_complete(processor.do_embedding(job_data)) 
    return ["Finished"] 