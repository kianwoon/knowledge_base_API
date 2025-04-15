#!/usr/bin/env python3
"""
Job processor implementations for the Worker module.
"""

from typing import Dict, Any
from loguru import logger

from app.worker.processors_file_common import EmbeddingFileProcessor

class EmbeddingSharepointProcessor(EmbeddingFileProcessor):
    """Processor for sharepoint text embedding jobs."""
    
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
            "owner": owner,  # Include owner in extra_data
            "sensitivity": job_data.get("sensitivity", "internal"),  # Include sensitivity in extra_data
            "source": self.job_type
        })

        fileSize = int(job_data.get("size", 0))

        binary = job_data.get("content_b64", None)
        if not binary:
            logger.warning("No content_b64 found in job data.")
            raise ValueError("No content_b64 found in job data.")
        
            return None
        job_status = job_data.get("analysis_status", None) 
        
        # Get file type from mimetype or filename if available
        file_type = None  #job_data.get("mimetype", "")
        filename = job_data.get("filename", "")
 
        # Try to extract extension from filename
        if "." in filename:
            file_type = "." + filename.split(".")[-1]
        else:
            logger.warning("Filename does not contain an extension.")


        results = await self.send_embedding(job_id, trace_id, file_type, fileSize, binary, job_status, extra_data)
        
        return results