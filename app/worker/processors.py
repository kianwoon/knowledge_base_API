#!/usr/bin/env python3
"""
Job processor implementations for the Worker module.
"""

import base64
from typing import Dict, Any, List
from loguru import logger

from app.core.const import JobType
from app.services.openai_service import openai_service
from app.worker.interfaces import JobProcessor, JobFactory
from app.utils.text_utils import html_to_markdown, convert_to_text


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
        
        return await openai_service.analyze_subjects(subjects, min_confidence, job_id, trace_id)


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
        
        return await openai_service.analyze_email(job_data, job_id, trace_id)


class EmbeddingProcessor(JobProcessor):
    """Processor for text embedding jobs."""
    
    async def process(self, job_data: Dict[str, Any], job_id: str, trace_id: str, owner: str = None) -> Dict[str, Any]:
        """
        Process a text embedding job.
        
        Args:
            job_data: Job data containing text to embed
            job_id: Job ID
            trace_id: Trace ID
            
        Returns:
            Processing results including the embedding vector(s)
        """
        # Get email body HTML and convert to markdown for better processing
        mail_body_html = job_data.get("raw_text", "")
        mail_body_md = html_to_markdown(mail_body_html)

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
        
        # Get custom chunk parameters if provided
        chunk_size = job_data.get("chunk_size", None)
        chunk_overlap = job_data.get("chunk_overlap", None)
        
        logger.info(
            f"Processing embedding job {job_id}, trace_id: {trace_id}, original length: {original_length}, processed length: {processed_length}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        # Call the embeding_text method from OpenAI service
        # If custom chunking parameters were provided, they will be passed to the service
        if chunk_size or chunk_overlap:
            # Create custom chunker with provided parameters
            from app.utils.text_chunker import TextChunker
            custom_chunker = TextChunker(chunk_size, chunk_overlap)
            openai_service.text_chunker = custom_chunker
            
        result = await openai_service.embeding_text(text)
        
        # Define extra data fields to include with the embedding
        extra_data = {
            "extra_data": {
                "owner": job_data.get("owner", ""),
                "type": job_data.get("type", ""),
                "sensitivity": job_data.get("sensitivity", ""),
                "subject": job_data.get("subject", ""),
                "date": job_data.get("date", ""),
                "sender": job_data.get("sender", ""),
                "source": job_data.get("source", ""),
                "source_id": job_id,
                "filename": job_data.get("filename", ""),
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
                        file_type = filename.split(".")[-1]
                
                # Extract text from supported file types
                if file_type and attachment.get("content_base64"):
                    # Decode base64 content
                    try:
                        # Convert base64 content to text
                        text_attachment = convert_to_text(attachment["content_base64"], file_type)
                        
                        # Only process if we have text content
                        if text_attachment:
                            logger.info(
                                f"Processing attachment: {attachment.get('filename', 'unnamed')}, size: {len(text_attachment)} chars",
                                extra={"job_id": job_id, "trace_id": trace_id}
                            )
                            
                            # Generate embedding for attachment
                            attachment_result = await openai_service.embeding_text(text_attachment)
                            
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


class DefaultJobFactory(JobFactory):
    """Default implementation of the JobFactory interface."""
    
    def get_processor(self, job_type: str) -> JobProcessor:
        """
        Get job processor for the given job type.
        
        Args:
            job_type: Job type
            
        Returns:
            Job processor
        """
        if job_type == JobType.SUBJECT_ANALYSIS.value:
            return SubjectAnalysisProcessor()
        elif job_type == JobType.EMBEDDING.value:
            return EmbeddingProcessor()
        else:
            # Default to email analysis
            return EmailAnalysisProcessor()