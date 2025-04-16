
from celery import shared_task
from loguru import logger
 
# from app.worker.processors_s3 import EmbeddingS3FileProcessor 
from app.worker.processors_file_s3 import EmbeddingS3Processor as Processor

from app.celery.worker import get_or_create_event_loop
 

source = "_aws_s3_knowledge"
job_type = "aws_s3"

pending_task_name = "aws_s3_embedding.get_pending_jobs"
task_name = "aws_s3_embedding.task_processing"

queue_name = "background"

@shared_task(name=pending_task_name, queue=queue_name)
def get_pending_jobs():
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """
    logger.info("Check pending jobs.")
    
    processor = Processor(source_repository=source, job_type=job_type, task_name=task_name)
 
    loop = get_or_create_event_loop()
    results = loop.run_until_complete(processor.schedule_task())
    

    logger.info("Pending jobs retrieved: " + str(results))
    return results


@shared_task(name=task_name, queue=queue_name)
def process_embedding(job_data: str):
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """ 

    logger.info("Processing embedding task " + job_data)
    processor = Processor(source_repository=source, job_type=job_type)
     
    loop = get_or_create_event_loop()
    loop.run_until_complete(processor.do_embedding(job_data)) 
    return ["Finished"]