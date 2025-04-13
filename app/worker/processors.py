#!/usr/bin/env python3
"""
Job processor implementations for the Worker module.
"""

from typing import Dict, Any
from loguru import logger

from app.core.const import JobType
from app.services.openai_service import OpenAIService
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
                        file_type = filename.split(".")[-1]
                
 

                # Extract text from supported file types
                if file_type and attachment.get("content_base64"):
                    # Decode base64 content
                    try:
                        attachment_results = await EmbeddingFileProcessor().process(attachment, job_id, trace_id, owner)   
                         
                        # Add to results list
                        results.append(attachment_results)
                        
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


class EmbeddingFileProcessor(JobProcessor):
    """Processor for SharePoint text embedding jobs."""
    
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

        fileSize = job_data.get("size_bytes", "")

        binary = job_data.get("content_b64", None)

        job_status = job_data.get("analysis_status", None)
        # if job_status and job_status != "processing":
        #     return


        # Add size checks and limits
        MAX_FILE_SIZE = 10000000  # Limit text processing to 10M chars
        if fileSize and len(binary) > MAX_FILE_SIZE:  
            raise ValueError(f"Input size exceeds the maximum allowed limit of {MAX_FILE_SIZE} characters.")

        # Define extra data fields to include with the embedding
        extra_data = {
            "extra_data": {
                "owner": owner,
                "type": job_data.get("type", ""),
                "sensitivity": job_data.get("sensitivity", "internal"),
                "lastUpdate": job_data.get("lastUpdate", ""), 
                "source": "sharepoint",
                "source_id": job_id,
                "filename": job_data.get("file_name", ""),
                "tags": job_data.get("tags", []),
            } 
        }

        results = []
           
        logger.info(
            f"Processing embedding job {job_id}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
      
        # Get file type from mimetype or filename if available
        file_type = job_data.get("mimetype", "")
        if not file_type and "file_name" in job_data:
            # Try to extract extension from filename
            filename = job_data.get("file_name", "")
            if "." in filename:
                file_type = filename.split(".")[-1]
        
        # Extract text from supported file types
        if file_type and binary:
            # Decode base64 content
            try:
                # Convert base64 content to text
                text_file = convert_to_text(binary, filename)
                
                # Only process if we have text content
                if text_file:
                    logger.info(
                        f"Processing attachment: {job_data.get('file_name', 'unnamed')}, size: {len(text_file)} chars",
                        extra={"job_id": job_id, "trace_id": trace_id}
                    )
                    
                    # Generate embedding for attachment
                    embedding_results = await openai_service.embedding_text(text_file)

                    # Add the extra_data to the attachment result
                    embedding_results.update(extra_data)
                    
                    # Add to results list
                    results.append(embedding_results)
                    
                    logger.info(
                        f"Completed embedding for attachment: {job_data.get('filename', 'unnamed')}",
                        extra={"job_id": job_id, "trace_id": trace_id}
                    )
            except Exception as e:
                logger.error(
                    f"Error processing attachment {job_data.get('filename', 'unnamed')}: {str(e)}",
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
            return EmbeddingMailProcessor()
        else:
            # Default to email analysis
            return EmailAnalysisProcessor()