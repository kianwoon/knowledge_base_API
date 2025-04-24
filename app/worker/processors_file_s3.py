#!/usr/bin/env python3
"""
Job processor implementations for the Worker module.
"""

from typing import Dict, Any
from loguru import logger

from app.worker.processors_file_common import EmbeddingFileProcessor

class EmbeddingS3Processor(EmbeddingFileProcessor):
    """Processor for AWS S3 text embedding jobs."""
    
    async def get_pending_jobs(self) -> Dict[str, Any]:

        # Use the instance repository instead of creating a new one
        
        filter = ""
        
        payload = ["id", "analysis_status"]

        pending_jobs = await self.source_repository.get_pending_jobs(self.job_type)                 
  
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

        extra_data = {
            "extra_data": {k: v for k, v in job_data.items() if k != "content_b64"}
        }

        extra_data["extra_data"].update({
            "owner": owner,  # Include owner in extra_data
            "sensitivity": job_data.get("sensitivity", "internal"),  # Include sensitivity in extra_data
            "source": self.job_type
        })

        fileSize = int(job_data.get("size", 0))

        binary = job_data.get("content_b64", None)

        job_status = job_data.get("analysis_status", None) 
        
        # Get file type from content_type or filename if available
        file_type = job_data.get("content_type", "")
        filename = job_data.get("original_filename", "")

        if not file_type and "original_filename" in job_data:
            # Try to extract extension from filename
            if "." in filename:
                file_type = "." + filename.split(".")[-1]
                
        results = await self.send_embedding(job_id, trace_id, file_type, fileSize, binary, job_status, extra_data)
        
        return results