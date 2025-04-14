import asyncio
import json
from celery import shared_task

from app.worker.notifier import DefaultWebhookNotifier 
from app.worker.processors import SubjectAnalysisProcessor
from loguru import logger 

@shared_task(name="task_email.process_subjects")
def process_subjects(job_id: str, job_data: str, client_id: str, trace_id: str = None):
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