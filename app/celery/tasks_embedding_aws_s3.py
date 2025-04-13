
from celery import shared_task
from loguru import logger
 
from app.worker.processors_s3 import EmbeddingS3FileProcessor 
from app.celery.worker import get_or_create_event_loop
 

@shared_task(name="aws_s3_embedding.get_pending_jobs")
def get_pending_jobs():
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """
    logger.info("Check pending jobs.")
    
    processor = EmbeddingS3FileProcessor(source_repository="_aws_s3_knowledge", job_type="aws_s3", task_name="aws_s3_embedding.task_processing")
 
    loop = get_or_create_event_loop()
    results = loop.run_until_complete(processor.schedule_task())
    

    logger.info("Pending jobs retrieved: " + str(results))
    return results


@shared_task(name="aws_s3_embedding.task_processing")
def process_embedding(job_data: str):
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """ 

    logger.info("Processing embedding task " + job_data)
    processor = EmbeddingS3FileProcessor(source_repository="_aws_s3_knowledge", job_type="aws_s3")
     
    loop = get_or_create_event_loop()
    loop.run_until_complete(processor.do_embedding(job_data)) 
    return ["Finished"]