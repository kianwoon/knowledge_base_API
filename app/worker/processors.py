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
        logger.info(
            f"Processing email analysis job {job_id}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        return await openai_service.analyze_email(job_data, job_id, trace_id)


class EmbeddingProcessor(JobProcessor):
    """Processor for text embedding jobs."""
    
    async def process(self, job_data: Dict[str, Any], job_id: str, trace_id: str) -> Dict[str, Any]:
        """
        Process a text embedding job.
        
        Args:
            job_data: Job data containing text to embed
            job_id: Job ID
            trace_id: Trace ID
            
        Returns:
            Processing results including the embedding vector(s)
        """
 
        text = job_data.get("subject", "") + job_data.get("raw_text", "")
        if not text: 
          logger.info(f"No text provided for embedding, job {job_id}, trace_id: {trace_id}, text length: {len(text)}")
          return {"job_id": job_id, "trace_id": trace_id, "embedding": None}
        
        # Get custom chunk parameters if provided
        chunk_size = job_data.get("chunk_size", None)
        chunk_overlap = job_data.get("chunk_overlap", None)
        
        logger.info(
            f"Processing embedding job {job_id}, trace_id: {trace_id}, text length: {len(text)}",
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
        
        # Add job and trace IDs to the result
        result["job_id"] = job_id
        result["trace_id"] = trace_id
        
        # Log completion
        chunk_count = result.get("chunk_count", 1)
        logger.info(
            f"Completed embedding job {job_id}, trace_id: {trace_id}, chunks: {chunk_count}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        return result


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