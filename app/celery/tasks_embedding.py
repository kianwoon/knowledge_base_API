import asyncio
import json
import time
from celery import shared_task
from loguru import logger

from app.core.snowflake import generate_id
from app.worker.processors import EmbeddingProcessor
from app.worker.repository_qdrant import QdrantJobRepository


@shared_task(name="task_embedding.get_pending_jobs")
def get_pending_jobs():
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """
    logger.info("Check pending jobs.")
    
    async def process_pending_jobs():
        repository = QdrantJobRepository()
        pending_jobs = await repository.get_pending_jobs()
        
        if not pending_jobs:
            logger.info("No pending jobs found")
            return []
        
        logger.info(f"Found {len(pending_jobs)} pending jobs")
        for job_data in pending_jobs:
            logger.info(f"Processing job: {job_data}")  
            try:
                job_id = job_data.split(":")[1] if ":" in job_data else None
                owner = job_data.split(":")[2] if len(job_data.split(":")) > 2 else None

                if not job_id or owner is None:
                    err_msg = f"Job ID or owner is missing: {job_data}."
                    logger.error(err_msg)
                    await repository.update_job_status(job_id, err_msg, owner, None)
                    continue
                
                # # Add atomic job claiming to prevent race conditions
                # claimed = await repository.claim_job(job_id, owner)
                # if not claimed:
                #     logger.info(f"Job {job_id} was already claimed by another worker, skipping")
                #     continue
                
                # Now the job is exclusively claimed by this worker
                await repository.update_job_status(job_id, "scheduled", owner, None)
                logger.info(f"Processing Job ID: {job_id}, Owner: {owner}")
                
                # Schedule the task without awaiting it (use synchronous Celery API)
                
                task = process_embedding.apply_async(args=(job_id, owner), task_id=job_id)

                logger.info(f"Scheduled task with ID: {task.id} for job {job_id}")
                await repository.update_job_status(job_id, "processing", owner, None)

            except Exception as e:
                logger.error(f"Error scheduling task for job {job_data}: {str(e)}")
                if job_id and owner:
                    await repository.update_job_status(job_id, f"error: {str(e)}", owner, None)
 
        return pending_jobs

    # Use a single asyncio.run call for all async operations
    result = asyncio.run(process_pending_jobs())
    # logger.info("Finished executing get_pending_jobs task.")
    return result


@shared_task(name="task_embedding.task_processing")
def process_embedding(job_id: str, owner: str):
    """
    Process embedding task.
    
    Args:
        data: The data containing information for embedding processing.
    """
    logger.info(f"Starting process_embedding with job_id: {job_id}, owner: {owner}")

    async def process_job():
        try:
            trace_id = generate_id()
            repository = QdrantJobRepository()
            processor = EmbeddingProcessor()
            
            # Get job data and update status
            job_data_json = await repository.get_job_data(job_id, owner)
            
            # Log full job data for debugging
            logger.info(f"Job data length: {len(job_data_json)}, job_id: {job_id}, owner: {owner}")
            
            job_json = json.loads(job_data_json)

            # Process job
            results = await processor.process(job_json, job_id, trace_id, owner)

            # Store results
            await repository.store_job_results(job_id, results, owner)
            
            # Update job status
            await repository.update_job_status(job_id, "completed", owner)
            
            logger.info(f"Completed process_embedding task for job {job_id}, owner: {owner}")
            
            # return results
            
        except Exception as e:
            logger.error(f"Error in process_embedding task: {str(e)} for job {job_id}, owner: {owner}")
            await repository.update_job_status(job_id, f"error: {str(e)}", owner)
            raise
    

    logger.info(f"Finished process_embedding with job_id: {job_id}, owner: {owner}")

    # Use a single asyncio.run call to manage the event loop properly
    asyncio.run(process_job())
    return ["Finished"]



