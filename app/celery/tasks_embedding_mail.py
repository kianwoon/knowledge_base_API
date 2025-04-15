 
from celery import shared_task
from loguru import logger
 
from app.worker.processors_file_mail import EmbeddingMailProcessor as Processor

from app.celery.worker import  get_or_create_event_loop

@shared_task(name="mail_embedding.get_pending_jobs")
def get_pending_jobs():
    """
    Process embedding task.
    
    Args:
        self: The Celery task instance (automatically provided by Celery)
    """
    logger.info("Check pending jobs.")
    
    processor = Processor(source_repository="_email_knowledge", job_type="email", task_name="mail_embedding.task_processing")
 
    loop = get_or_create_event_loop()
    results = loop.run_until_complete(processor.schedule_task())
    

    logger.info("Pending jobs retrieved: " + str(results)) 
    return results



@shared_task(name="mail_embedding.task_processing")
def process_embedding(job_data: str):
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """ 

    logger.info("Processing embedding task " + job_data)
    processor = Processor(source_repository="_email_knowledge", job_type="email")
     
    loop = get_or_create_event_loop()
    loop.run_until_complete(processor.do_embedding(job_data)) 
    return ["Finished"]



