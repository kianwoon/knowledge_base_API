#!/usr/bin/env python3
"""
Job processor implementations for the Worker module.
"""

from typing import Dict, Any
from loguru import logger

from app.core.const import JobType
from app.services.openai_service import openai_service
from app.worker.interfaces import JobProcessor, JobFactory


class SubjectAnalysisProcessor(JobProcessor):
    """Processor for subject analysis jobs."""
    
    async def process(self, job_data: Dict[str, Any], job_id: str, trace_id: str) -> Dict[str, Any]:
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
    
    async def process(self, job_data: Dict[str, Any], job_id: str, trace_id: str) -> Dict[str, Any]:
        """
        Process an email analysis job.
        
        Args:
            job_data: Job data
            job_id: Job ID
            trace_id: Trace ID
            
        Returns:
            Processing results
        """
        # Handle 'from_' field if present (convert to 'from' for compatibility)
        if 'from_' in job_data and 'from' not in job_data:
            logger.info(
                f"Converting 'from_' to 'from' for job {job_id}, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}
            )
            job_data['from'] = job_data['from_']
        elif 'from' not in job_data and 'from_' not in job_data:
            logger.error(
                f"Neither 'from' nor 'from_' found in email data for job {job_id}, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}
            )
            # Add a default 'from' field to prevent errors
            job_data['from'] = {'name': 'Unknown', 'email': 'unknown@example.com'}
        
        logger.info(
            f"Processing email analysis job {job_id}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        return await openai_service.analyze_email(job_data, job_id, trace_id)


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
        else:
            # Default to email analysis
            return EmailAnalysisProcessor()