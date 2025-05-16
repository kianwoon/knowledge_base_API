#!/usr/bin/env python3
"""
Job processor implementations for the Worker module.
"""

from typing import Dict, Any
from loguru import logger

from app.services.openai_service import OpenAIService
from app.worker.interfaces import JobProcessor
 


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
