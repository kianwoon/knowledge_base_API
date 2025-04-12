import asyncio
import json
import time
from typing import Any, Dict, List
from celery import shared_task

from app.worker.notifier import DefaultWebhookNotifier 
from app.worker.processors import SubjectAnalysisProcessor
from loguru import logger
from app.services.openai_service import openai_service


@shared_task(name="app.tasks.add")
def add(x, y):
    """
    A simple task that adds two numbers together.
    This demonstrates a basic Celery task.
    """
    # Simulate a time-consuming task
    time.sleep(2)
    return x + y

@shared_task(name="task_email.process_subjects", bind=True)
def process_subjects(self, job_id: str, job_data: str, client_id: str, trace_id: str = None):
    """
    Process email subjects analysis task.
    
    Args:
        job_id: Job ID
        job_data: Job data
        client_id: Client ID
        trace_id: Trace ID
    """
    try:
        
        # Log the start of processing
        logger.info(
            f"Processing subject analysis job {job_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        async def process_subjects():
            try:
                # Parse job data
                parsed_data = json.loads(job_data)

                analysis_results = await SubjectAnalysisProcessor().process(parsed_data, job_id, trace_id, client_id) 
                
                await DefaultWebhookNotifier().send_notification(analysis_results, job_id, trace_id)

                return analysis_results
            except Exception as e:
                logger.error(
                    f"Error processing subject analysis job {job_id}: {str(e)}",
                    extra={"job_id": job_id, "trace_id": trace_id}
                )
                raise

        results = asyncio.run(process_subjects())
        
        logger.info(
            f"Completed subject analysis for job {job_id}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        return results
        
    except Exception as e:
        logger.error(
            f"Error processing subject analysis job {job_id}: {str(e)}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        raise