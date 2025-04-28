#!/usr/bin/env python3
"""
Job processor implementations for the Worker module.
"""

import json
from typing import Dict, Any, List
from loguru import logger

from app.core.snowflake import generate_id

from app.services.embedding_service_milvus import embeddingService as embeddingServiceMilvus    

from app.worker.interfaces import JobProcessor
from app.utils.text_utils import convert_to_text
from app.worker.repository_milvus import MilvusRepository
from app.worker.repository_postgres import PostgresRepository
from app.core.CloudflareR2 import download_file
from app.celery.worker import celery

class EmbeddingFileProcessor(JobProcessor):
    """Processor for AWS S3 text embedding jobs."""

    def __init__(self, source_repository: str, job_type: str, task_name: str = None) -> None:
        """
        Initialize the processor with a specific source repository.
        Args:
            source_repository: The source repository for the processor.
            job_type: The type of job for the processor.
            task_name: The name of the task for the processor.
        """
        
        self.target_repository = MilvusRepository()
        self.job_type = job_type
        self.task_name = task_name
        self.source_repository = PostgresRepository()
    
    async def __aenter__(self):
        """Context manager entry - connect to repositories."""
        if hasattr(self.source_repository, 'connect_with_retry'):
            await self.source_repository.connect_with_retry()
        elif hasattr(self.source_repository, 'connect'):
            await self.source_repository.connect()
            
        if hasattr(self.target_repository, 'connect'):
            await self.target_repository.connect()
        elif hasattr(self.target_repository, 'connect_with_retry'):
            await self.target_repository.connect_with_retry()
            
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close repository connections."""
        await self.close()
        
    async def close(self):
        """Close all repository connections properly."""
        if hasattr(self.source_repository, 'close'):
            await self.source_repository.close() 
        logger.info("Closed all repository connections")

    async def process(self, job_data, job_id, trace_id, owner = None):        
        logger.info(f"Processing job with ID: {job_id}, trace_id: {trace_id}, owner: {owner}")
       

    async def do_embedding(self, job_data: str) -> None:
        """
        Process embedding task.
        Args:
            job_data: The data containing information for embedding processing.
        """
        try:
            # Connect to repositories with method checking
            if hasattr(self.source_repository, 'connect_with_retry'):
                await self.source_repository.connect_with_retry()
            elif hasattr(self.source_repository, 'connect'):
                await self.source_repository.connect()
                
            if hasattr(self.target_repository, 'connect'):
                await self.target_repository.connect()
            elif hasattr(self.target_repository, 'connect_with_retry'):
                await self.target_repository.connect_with_retry()
            
            job_type, job_id, owner = job_data.split(":")

            logger.info(f"Starting do_embedding with job_id: {job_id}, owner: {owner}")
            trace_id = generate_id() 
            # Get job data and update status
            job_data_json = await self.source_repository.get_job_data(int(job_id), owner)
            
            # Log full job data for debugging
            logger.info(f"Job data length: {len(job_data_json)}, job_id: {job_id}, owner: {owner}")
            
            job_json = json.loads(job_data_json)

            # Process job
            results = await self.start_embedding(job_json, job_id, trace_id, owner)

            # Store results using a new connection with context manager
            async with MilvusRepository() as milvus:
                await milvus.store_job_results(job_id, results, owner)
            
            # Update job status
            await self.source_repository.update_job_status(job_id, "completed", owner)
            
            logger.info(f"Completed do_embedding task for job {job_data}")
        finally:
            # Always close connections when done
            await self.close()
    

    async def schedule_task(self) -> None:
        try:
            # Connect to repositories
            await self.source_repository.connect_with_retry()
            
            pending_jobs = await self.source_repository.get_pending_jobs(self.job_type)   
            # pending_jobs = await self.get_pending_jobs()
            if not pending_jobs:
                logger.info(f"No pending jobs{ self.job_type } found for processing.")
                return []
            
            logger.info(f"Found {len(pending_jobs)} pending jobs")
            for job_data in pending_jobs:
                logger.info(f"Processing job: {job_data}")  
                try:
                    
                    job_type, job_id, owner = job_data.split(":")

                    # Schedule the task without awaiting it (use synchronous Celery API)
                    task = celery.send_task(self.task_name, kwargs={"job_data": job_data}, task_id=job_id)

                    logger.info(f"Scheduled task with ID: {task.id} for job {job_id}")

                except Exception as e:
                    logger.error(f"Error scheduling task for job {job_data}: {str(e)}")
                    if job_id and owner:
                        await self.source_repository.update_job_status(job_id, f"error: {str(e)}", owner)

            return pending_jobs
        finally:
            # Always close connections when done
            await self.close()
    
    
    async def send_embedding(self, job_id:str, trace_id: str , file_type: str, fileSize: int, fileName: str, job_status: str, extra_data: Dict[str, Any]) -> List[Dict[str, Any]]:
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
            if job_status and job_status != "scheduled":
                raise ValueError(f"Job status is not 'scheduled': {job_status}")

            # Add size checks and limits
            MAX_FILE_SIZE = 10000000  # Limit text processing to 10M chars
            if fileSize > MAX_FILE_SIZE:  
                raise ValueError(f"Input size exceeds the maximum allowed limit of {MAX_FILE_SIZE} characters.")

            results = []
            
            logger.info(
                f"Processing embedding job {job_id}, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}            )
        
            
            # Extract text from supported file types
            if file_type and fileName:
                # Decode base64 content
                try:
                    # Convert base64 content to text
                    text_file = convert_to_text(fileName, file_type)

                    fileSize = len(text_file)
                    if fileSize > MAX_FILE_SIZE:  
                        raise ValueError(f"Job ID: {job_id} Trace ID:{trace_id}, input size exceeds the maximum allowed limit of {MAX_FILE_SIZE} characters.")
                    
                    # Only process if we have text content
                    if text_file:
                        logger.info(
                            f"Processing: {file_type}, size: {len(text_file)} chars",
                            extra={"job_id": job_id, "trace_id": trace_id}
                        )
   
                        # Generate embedding for attachment
                        embedding_results = await embeddingServiceMilvus.embedding_text(text_file)


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


    async def start_embedding(self, job_data: Dict[str, Any], job_id: str, trace_id: str, owner: str = None) -> Dict[str, Any]:
        """
        Process a text embedding job with resource limits.
        
        Args:
            job_data: Job data containing text to embed
            job_id: Job ID
            trace_id: Trace ID
            
        Returns:
            Processing results including the embedding vector(s)
        """

        extra_data = {
            "extra_data": {k: v for k, v in job_data.items() if k != "content_b64" and k != "analysis_status"}
        }

        extra_data["extra_data"].update({
            "sensitivity": job_data.get("sensitivity", "internal"),  # Include sensitivity in extra_data
        })


        
        fileSize = int(job_data.get("size_bytes", 0))
        binaryFile = job_data.get("r2_object_key", None)



        if not binaryFile:
            logger.warning("No content_b64 found in job data.")
            raise ValueError("No content_b64 found in job data.")
        

        job_status = job_data.get("status", None) 
        
        # Get file type from mimetype or filename if available
        file_type = None  #job_data.get("mimetype", "")
        filename = job_data.get("original_filename", "")
 
        # Try to extract extension from filename
        if "." in filename:
            file_type = "." + filename.split(".")[-1]
        else:
            logger.warning("Filename does not contain an extension.")

        if not ("application/pdf" in file_type or 
              file_type.endswith(".pdf") or 
              file_type == "application/msword" or 
              file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or
              file_type.endswith(".docx") or file_type.endswith(".doc") or 
              file_type == "word" or 
              file_type == "application/vnd.ms-excel" or
              file_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" or
              file_type.endswith(".xlsx") or file_type.endswith(".xls") or
              file_type == "excel" or 
              any(x in file_type for x in ["text/plain", "text/csv", "text/markdown", "text/tab-separated-values",
                                         "text/", "txt", "csv", "md", "tsv"])  or 
              any(x in file_type for x in ["application/vnd.ms-powerpoint", 
                                         "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                         "powerpoint", "ppt", "pptx"]) or 
              "text/html" in file_type or "html" in file_type):
            await self.source_repository.store_job_error(job_id, "File type is not supported.")
            raise ValueError(f"File type {file_type} is not supported.")
        
        try:
            file = download_file(binaryFile, job_id, filename)
            if not file:
                await self.source_repository.store_job_error(job_id, "File could not be downloaded")
                raise ValueError(f"Job {job_id} Error: File could not be downloaded.")
        except Exception as e:
            error_message = f"Error downloading file: {str(e)}"
            logger.error(f"Job {job_id}: {error_message}")
            await self.source_repository.store_job_error(job_id, error_message)
            raise ValueError(f"Job {job_id} Error: {error_message}")
        
        results = await self.send_embedding(job_id, trace_id, file_type, fileSize, file, job_status, extra_data)
        

        return results
