#!/usr/bin/env python3
"""
Job processor implementations for the Worker module.
"""

import json
from typing import Dict, Any
from loguru import logger

from app.core.snowflake import generate_id
from app.services.openai_service import OpenAIService
from app.worker.interfaces import JobProcessor
from app.utils.text_utils import convert_to_text
from app.worker.repository_qdrant import QdrantRepository

from app.celery.worker import celery

class EmbeddingS3FileProcessor(JobProcessor):
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


    async def do_embedding(self, job_data: str) -> None:
        """
        Process embedding task.
        Args:
            data: The data containing information for embedding processing.
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
        results = await self.process(job_json, job_id, trace_id, owner)

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

    async def get_pending_jobs(self) -> Dict[str, Any]:

        # Use the instance repository instead of creating a new one
        
        filter = {
                    "must": [
                            {"key": "analysis_status", "match": {"value": "pending"}}
                            ]
                }
        
        payload = ["id", "analysis_status"]

        pending_jobs = await self.repository.get_pending_jobs(self.job_type, filter, payload)                 
  
        if not pending_jobs:
            logger.info("No pending jobs found for processing.")
            return []
        
        logger.info(f"Found {len(pending_jobs)} pending jobs")
        return pending_jobs
    

    async def process(self, job_data: Dict[str, Any], job_id: str, trace_id: str, owner: str = None) -> Dict[str, Any]:
        """
        Process a text embedding job with resource limits.
        
        Args:
            job_data: Job data containing text to embed
            job_id: Job ID
            trace_id: Trace ID
            
        Returns:
            Processing results including the embedding vector(s)
        """
        openai_service = OpenAIService() 

        fileSize = int(job_data.get("size", 0))

        binary = job_data.get("content_b64", None)

        job_status = job_data.get("analysis_status", None)
        # if job_status and job_status != "processing":
        #     return


        # Add size checks and limits
        MAX_FILE_SIZE = 10000000  # Limit text processing to 10M chars
        if fileSize > MAX_FILE_SIZE:  
            raise ValueError(f"Input size exceeds the maximum allowed limit of {MAX_FILE_SIZE} characters.")

                # Define extra data fields to include with the embedding
        extra_data = {
            "extra_data": {
                "owner": owner,
                "s3_bucket": job_data.get("s3_bucket", ""),
                "s3_key": job_data.get("s3_key", ""),
                "sensitivity": job_data.get("sensitivity", "internal"),
                "lastUpdate": job_data.get("lastUpdate", ""), 
                "source": job_data.get("source", ""), 
                "source_id": job_id,
                "filename": job_data.get("original_filename", ""),
                "size": job_data.get("size", ""),
                "content_type": job_data.get("content_type", ""),
                "last_modified": job_data.get("last_modified", ""),
                "ingested_at": job_data.get("ingested_at", ""),
                "tags": job_data.get("tags", []),
            } 
        }

        results = []
           
        logger.info(
            f"Processing embedding job {job_id}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
      
        # Get file type from content_type or filename if available
        file_type = job_data.get("content_type", "")
        filename = job_data.get("original_filename", "")

        if not file_type and "original_filename" in job_data:
            # Try to extract extension from filename
            if "." in filename:
                file_type = "." + filename.split(".")[-1]
        
        # Extract text from supported file types
        if file_type and binary:
            # Decode base64 content
            try:
                # Convert base64 content to text
                text_file = convert_to_text(binary, file_type)

                fileSize = len(text_file)
                if fileSize > MAX_FILE_SIZE:  
                    raise ValueError(f"Input {filename} size exceeds the maximum allowed limit of {MAX_FILE_SIZE} characters.")
                
                # Only process if we have text content
                if text_file:
                    logger.info(
                        f"Processing: {filename}, size: {len(text_file)} chars",
                        extra={"job_id": job_id, "trace_id": trace_id}
                    )
                    
                    # Generate embedding for attachment
                    embedding_results = await openai_service.embedding_text(text_file)

                    # Add the extra_data to the attachment result
                    embedding_results.update(extra_data)
                    
                    # Add to results list
                    results.append(embedding_results)
                    
                    logger.info(
                        f"Completed embedding for: {filename}",
                        extra={"job_id": job_id, "trace_id": trace_id}
                    )
            except Exception as e:
                logger.error(
                    f"Error processing {filename}: {str(e)}",
                    extra={"job_id": job_id, "trace_id": trace_id}
                )
                raise

        return results