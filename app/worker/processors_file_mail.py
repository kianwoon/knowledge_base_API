#!/usr/bin/env python3
"""
Job processor implementations for the Worker module.
"""

from typing import Dict, Any
from loguru import logger

from app.services.embedding_service import embeddingService
from app.services.openai_service import OpenAIService
from app.utils.text_utils import convert_to_text, html_to_markdown
from app.worker.processors_file_common import EmbeddingFileProcessor

class EmbeddingMailProcessor(EmbeddingFileProcessor):
    """Processor for mail text embedding jobs."""
    
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

        # extra_data = {
        #     "extra_data": {k: v for k, v in job_data.items() if k != "content_b64" and k != "analysis_status"}
        # }

        # extra_data["extra_data"].update({
        #     "owner": owner,  # Include owner in extra_data
        #     "sensitivity": job_data.get("sensitivity", "internal"),  # Include sensitivity in extra_data
        #     "source": self.job_type
        # })



         # Get email body HTML and convert to markdown for better processing
        mail_body_html = job_data.get("raw_text", "")
        
        # Add size checks and limits
        MAX_TEXT_SIZE = 1000000  # Limit text processing to 1M chars
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
 
        result = await embeddingService.embedding_text(text)


        extra_data = {} 
        
        # Define extra data fields to include with the embedding
        extra_data.update({
            "extra_data": {
                "owner": job_data.get("owner", ""),
                "type": job_data.get("type", ""),
                "sensitivity": job_data.get("sensitivity", "internal"),
                "subject": job_data.get("subject", ""),
                "date": job_data.get("date", ""),
                "sender": job_data.get("sender", ""),
                "source": job_data.get("source", ""),
                "source_id": job_id, 
                "tags": job_data.get("tags", []),
            } 
        })

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
                filename = attachment.get("filename", "")
                binary = attachment.get("content_base64", None) 
                fileSize = int(attachment.get("size", 0))
                job_status = attachment.get("analysis_status", None)


                if not file_type and "filename" in attachment:
                    # Try to extract extension from filename                    
                    if "." in filename:
                        file_type = "." + filename.split(".")[-1]
                    else:
                        logger.warning("Attachment filename does not contain an extension.")                 
 
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
                            # Create attachment-specific extra data by copying the original
                            attachment_extra_data = {
                                "extra_data": {**extra_data["extra_data"]}  # Deep copy using dict unpacking
                            }
                                                        
                             
                            attachment_extra_data["extra_data"].update({
                                "filename": filename,  # Include owner in extra_data
                                "filensize": fileSize,  # Include size in extra_data
                            })

                            # Generate embedding for attachment
                            # attachment_result = await openai_service.embedding_text(text_attachment)

                            attachment_results = await self.send_embedding(job_id, trace_id, file_type, fileSize, binary, job_status, attachment_extra_data)
                             
                            # Add to results list
                            results.extend(attachment_results)
                            
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