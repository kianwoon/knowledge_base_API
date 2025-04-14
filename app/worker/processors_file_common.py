#!/usr/bin/env python3
"""
Job processor implementations for the Worker module.
"""

import json
from typing import Dict, Any, List
from loguru import logger

from app.core.snowflake import generate_id
from app.services.openai_service import OpenAIService
from app.worker.interfaces import JobProcessor
from app.utils.text_utils import convert_to_text
from app.worker.repository_qdrant import QdrantRepository

from app.celery.worker import celery

class EmbeddingFileProcessor(JobProcessor):
    """Processor for AWS S3 text embedding jobs."""

    def __init__(self, source_repository: str = "_aws_s3_knowledge", job_type: str = "aws_s3", task_name: str = "aws_s3_embedding.task_processing") -> None:
        """
        Initialize the processor with a specific source repository.
        Args:
            source_repository: The source repository for the processor.
        """
        
        self.repository = QdrantRepository(source_repository)
        self.job_type = job_type
        self.task_name = task_name
        self.source_repository = source_repository

    async def process(self, job_data, job_id, trace_id, owner = None):        
        logger.info(f"Processing job with ID: {job_id}, trace_id: {trace_id}, owner: {owner}")
       

    async def do_embedding(self, job_data: str) -> None:
        """
        Process embedding task.
        Args:
            job_data: The data containing information for embedding processing.
        """
        job_type, job_id, owner = job_data.split(":")

        logger.info(f"Starting do_embedding with job_id: {job_id}, owner: {owner}")
        trace_id = generate_id() 
        # Get job data and update status
        job_data_json = await self.repository.get_job_data(job_id, owner)
        
        # Log full job data for debugging
        logger.info(f"Job data length: {len(job_data_json)}, job_id: {job_id}, owner: {owner}")
        
        job_json = json.loads(job_data_json)

        # Process job
        results = await self.start_embedding(job_json, job_id, trace_id, owner)

        # Store results
        await self.repository.store_job_results(job_id, results, owner)
        
        # Update job status
        await self.repository.update_job_status(job_id, "completed", owner)
        
        logger.info(f"Completed do_embedding task for job {job_data}")
    

    async def schedule_task(self) -> None:
        pending_jobs = await self.get_pending_jobs()
        if not pending_jobs:
            logger.info(f"No pending jobs{ self.source_repository } found for processing.")
            return []
        
        logger.info(f"Found {len(pending_jobs)} pending jobs")
        for job_data in pending_jobs:
            logger.info(f"Processing job: {job_data}")  
            try:
                
                job_type, job_id, owner = job_data.split(":")

                await self.repository.update_job_status(job_id, "scheduled", owner)
                logger.info(f"Processing Job ID: {job_id}, Owner: {owner}")
                
                # Schedule the task without awaiting it (use synchronous Celery API)
                
                # task = process_embedding.apply_async(args=[job_data], task_id=job_id)

                task = celery.send_task(self.task_name, kwargs={"job_data": job_data}, task_id=job_id)

                logger.info(f"Scheduled task with ID: {task.id} for job {job_id}")

                await self.repository.update_job_status(job_id, "processing", owner)

            except Exception as e:
                logger.error(f"Error scheduling task for job {job_data}: {str(e)}")
                if job_id and owner:
                    await self.repository.update_job_status(job_id, f"error: {str(e)}", owner)

        return pending_jobs  
    
    
    async def send_embedding(self, job_id:str, trace_id: str , file_type: str, fileSize: int, binary: str, job_status: str, extra_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Start the embedding process for a job.
        Args:
            job_data: The data containing information for embedding processing.
            fileSize: Size of the file.
            binary: Base64 content of the file.
            job_status: Current status of the job.
            extra_data: Additional data for processing.
        """
        try: 
            if job_status and job_status != "processing":
                raise ValueError(f"Job status is not 'processing': {job_status}")

            # Add size checks and limits
            MAX_FILE_SIZE = 10000000  # Limit text processing to 10M chars
            if fileSize > MAX_FILE_SIZE:  
                raise ValueError(f"Input size exceeds the maximum allowed limit of {MAX_FILE_SIZE} characters.")

            results = []
            
            logger.info(
                f"Processing embedding job {job_id}, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}            )
        
            
            # Extract text from supported file types
            if file_type and binary:
                # Decode base64 content
                try:
                    # Convert base64 content to text
                    text_file = convert_to_text(binary, file_type)

                    fileSize = len(text_file)
                    if fileSize > MAX_FILE_SIZE:  
                        raise ValueError(f"Job ID: {job_id} Trace ID:{trace_id}, input size exceeds the maximum allowed limit of {MAX_FILE_SIZE} characters.")
                    
                    # Only process if we have text content
                    if text_file:
                        logger.info(
                            f"Processing: {file_type}, size: {len(text_file)} chars",
                            extra={"job_id": job_id, "trace_id": trace_id}
                        )

                        openai_service = OpenAIService() 
                        # Generate embedding for attachment
                        embedding_results = await openai_service.embedding_text(text_file)

                        # Add the extra_data to the attachment result
                        embedding_results.update(extra_data)
                        
                        # Add to results list
                        results.append(embedding_results)
                        
                        logger.info(
                            f"Completed embedding for Job ID: {job_id} Trace ID:{trace_id},",
                            extra={"job_id": job_id, "trace_id": trace_id}
                        )
                except Exception as e:
                    logger.error(
                        f"Error processing Job ID: {job_id} Trace ID:{trace_id},: {str(e)}",
                        extra={"job_id": job_id, "trace_id": trace_id}
                    )
                    raise

            return results
        
        except Exception as e:
            logger.error(f"Error in start_embedding: {str(e)}")
            raise
