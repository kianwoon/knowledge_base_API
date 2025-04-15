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
from app.utils.text_utils import html_to_markdown, convert_to_text
from app.worker.repository_qdrant import QdrantRepository

from app.celery.worker import celery


class SubjectAnalysisProcessor(JobProcessor):
    """Processor for subject analysis jobs."""
    
    async def process(self, job_data: Dict[str, Any], job_id: str, trace_id: str, owner: str = None ) -> Dict[str, Any]:
        """
        Process a subject analysis job.
        
        Args:
            job_data: Job data
            job_id: Job ID
            trace_id: Trace ID
            
        Returns:
            Processing results
        """
        subjects = job_data.get("subjects", [])
        min_confidence = job_data.get("min_confidence", None)
        
        if not subjects:
            raise Exception("No subjects provided for analysis")
        
        logger.info(
            f"Processing subject analysis job {job_id}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        return await OpenAIService().analyze_subjects(subjects, min_confidence, job_id, trace_id)


class EmailAnalysisProcessor(JobProcessor):
    """Processor for email analysis jobs."""
    
    async def process(self, job_data: Dict[str, Any], job_id: str, trace_id: str, owner: str = None) -> Dict[str, Any]:
        """
        Process an email analysis job.
        
        Args:
            job_data: Job data
            job_id: Job ID
            trace_id: Trace ID
            owner: Owner of the job (optional)
            
        Returns:
            Processing results
        """
        logger.info(
            f"Processing email analysis job {job_id}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        return await OpenAIService().analyze_email(job_data, job_id, trace_id)


class EmbeddingMailProcessor(JobProcessor):
    """Processor for text embedding jobs."""
    
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
        # Get email body HTML and convert to markdown for better processing
        mail_body_html = job_data.get("raw_text", "")
        
        # Add size checks and limits
        MAX_TEXT_SIZE = 500000  # Limit text processing to 500K chars
        if len(mail_body_html) > MAX_TEXT_SIZE:
            logger.warning(
                f"Email text too large ({len(mail_body_html)} chars), truncating to {MAX_TEXT_SIZE} chars",
                extra={"job_id": job_id, "trace_id": trace_id}
            )
            mail_body_html = mail_body_html[:MAX_TEXT_SIZE]
        
        mail_body_md = html_to_markdown(mail_body_html)

        # # Limit the size of the input to prevent CPU-intensive processing
        # max_input_size = 10000  # Example limit in characters
        # if len(mail_body_md) > max_input_size:
        #     raise ValueError(f"Input size exceeds the maximum allowed limit of {max_input_size} characters.")

        results = []

        # Mail body
        # Combine subject with cleaned body text
        subject = job_data.get("subject", "")
        text = f"{subject}\n\n{mail_body_md}" if subject else mail_body_md
        hasAttachment = job_data.get("has_attachments", False)


        # Track both original and processed text lengths
        original_length = len(mail_body_html)
        processed_length = len(text)

        if not text: 
            logger.info(f"No text provided for embedding, job {job_id}, trace_id: {trace_id}")
            return {"job_id": job_id, "trace_id": trace_id, "embedding": None}        
        
        logger.info(
            f"Processing embedding job {job_id}, trace_id: {trace_id}, original length: {original_length}, processed length: {processed_length}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        

        openai_service = OpenAIService()
            
        result = await openai_service.embedding_text(text)
        
        # Define extra data fields to include with the embedding
        extra_data = {
            "extra_data": {
                "owner": job_data.get("owner", ""),
                "type": job_data.get("type", ""),
                "sensitivity": job_data.get("sensitivity", "internal"),
                "subject": job_data.get("subject", ""),
                "date": job_data.get("date", ""),
                "sender": job_data.get("sender", ""),
                "source": job_data.get("source", ""),
                "source_id": job_id,
                "filename": job_data.get("filename", ""),
                "tags": job_data.get("tags", []),
            } 
        }
        # Add the extra_data fields to the result
        result.update(extra_data)
        
        # Add the completed result to results list
        results.append(result)

        # # Log completion for mail body
        chunk_count = result.get("chunk_count", 1)
        
        logger.info(
            f"Completed embedding mail body job {job_id}, trace_id: {trace_id}, chunks: {chunk_count}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )

        # Add attachment embeddings if present
        if hasAttachment:
            for attachment in job_data.get("attachments", []):
                # Get file type from mimetype or filename if available
                file_type = attachment.get("mimetype", "")
                if not file_type and "filename" in attachment:
                    # Try to extract extension from filename
                    filename = attachment.get("filename", "")
                    if "." in filename:
                        file_type = "." + filename.split(".")[-1]
                    else:
                        logger.warning("Attachment filename does not contain an extension.")
                 
                binary = attachment.get("content_base64", None)
                # Add size checks and limits
                # MAX_FILE_SIZE = 10000000  # Limit text processing to 10M chars
                # if binary and len(binary) > MAX_FILE_SIZE:
                #     logger.warning(
                #         f"Attachment size too large ({len(binary)} bytes), skipping attachment: {attachment.get('filename', 'unnamed')}",
                #         extra={"job_id": job_id, "trace_id": trace_id}
                #     )
                #     continue

                # Extract text from supported file types
                if file_type and binary:
                    # Decode base64 content
                    try:
                        # Convert base64 content to text
                        text_attachment = convert_to_text(binary, file_type)
                        
                        # Only process if we have text content
                        if text_attachment:
                            logger.info(
                                f"Processing attachment: {attachment.get('filename', 'unnamed')}, size: {len(text_attachment)} chars",
                                extra={"job_id": job_id, "trace_id": trace_id}
                            )
                            
                            # Generate embedding for attachment
                            attachment_result = await openai_service.embedding_text(text_attachment)
                            
                            # Create attachment-specific extra data by copying the original
                            attachment_extra_data = {
                                "extra_data": {**extra_data["extra_data"]}  # Deep copy using dict unpacking
                            }
                            
                            # Update with attachment-specific fields
                            attachment_extra_data["extra_data"]["filename"] = attachment.get("filename", "unknown")
                            
                            # Add the extra_data to the attachment result
                            attachment_result.update(attachment_extra_data)
                            
                            # Add to results list
                            results.append(attachment_result)
                            
                            logger.info(
                                f"Completed embedding for attachment: {attachment.get('filename', 'unnamed')}",
                                extra={"job_id": job_id, "trace_id": trace_id}
                            )


                    except Exception as e:
                        logger.error(
                            f"Error processing attachment {attachment.get('filename', 'unnamed')}: {str(e)}",
                            extra={"job_id": job_id, "trace_id": trace_id}
                        )
    
        return results
    
    def __init__(self, source_repository: str = "_email_knowledge", job_type: str = "email", task_name: str = "mail_embedding.task_processing") -> None:
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

                # await self.repository.update_job_status(job_id, "processing", owner)

            except Exception as e:
                logger.error(f"Error scheduling task for job {job_data}: {str(e)}")
                if job_id and owner:
                    await self.repository.update_job_status(job_id, f"error: {str(e)}", owner)
        return pending_jobs  

    async def get_pending_jobs(self) -> Dict[str, Any]:

        # Use the instance repository instead of creating a new one
        
        filter = {
                        "must": [
                            {"key": "analysis_status", "match": {"value": "pending"}},
                            {"key": "source", "match": {"value": "email"}}
                        ]
                }
        
        
        payload = ["job_id", "analysis_status", "type"]

        pending_jobs = await self.repository.get_pending_jobs(self.job_type, filter, payload)                 
  
        if not pending_jobs:
            logger.info("No pending jobs found for processing.")
            return []
        
        logger.info(f"Found {len(pending_jobs)} pending jobs")
        return pending_jobs