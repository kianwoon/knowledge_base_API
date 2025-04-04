#!/usr/bin/env python3
"""
Worker module for the Mail Analysis API.
"""

import json
import asyncio
import aiohttp
from typing import Dict, Any
from datetime import datetime
from loguru import logger

from app.core.config import config, get_timezone, localize_datetime
from app.core.redis import redis_client
from app.core.snowflake import generate_id
from app.core.const import JobType
from app.models.email import EmailSchema
from app.services.openai_service import openai_service


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    
    def default(self, obj):
        if isinstance(obj, datetime):
            # Ensure datetime has timezone info before converting to ISO format
            if obj.tzinfo is None:
                obj = localize_datetime(obj)
            return obj.isoformat()
        return super().default(obj)


async def send_webhook_notification(webhook_url: str,webhook_timeout:int, data: Dict[str, Any], job_id: str, trace_id: str):
    """
    Send webhook notification with job results.
    
    Args:
        webhook_url: Webhook URL to call
        data: Data to send in the webhook
        job_id: Job ID
        trace_id: Trace ID
    """
    try:
        logger.info(
            f"Sending webhook notification for job {job_id} to {webhook_url}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=webhook_timeout)  # Set a timeout for the request
            ) as response:
                response_text = await response.text()
                # Extract headers for logging
                headers_dict = dict(response.headers)
                response_log = json.dumps(response_text, indent=2)

                # Log the complete response with headers and status
                logger.info(
                    f"response: {response_log}",
                    extra={"job_id": job_id, "trace_id": trace_id}
                )
                if response.status >= 200 and response.status < 300:
                    logger.info(
                        f"Webhook notification sent successfully for job {job_id}, status: {response.status}, trace_id: {trace_id}",
                        extra={"job_id": job_id, "trace_id": trace_id}
                    )
                else:
                    # Extract headers for logging
                    headers_dict = dict(response.headers)
                    
                    # Log detailed error information
                    logger.error(
                        f"Failed to send webhook notification for job {job_id}, status: {response.status}, response_headers: {headers_dict}, response: {response_text[:2000] if len(response_text) > 2000 else response_text}, trace_id: {trace_id}",
                        extra={
                            "job_id": job_id, 
                            "trace_id": trace_id
                        }
                    )
    except aiohttp.ClientResponseError as e:
        logger.error(f"Error sending webhook notification for job {job_id}, trace_id: {trace_id} Client Response Error: {e.status} - {e.message}")
    except aiohttp.ClientConnectionError as e:
        logger.error(f"Error sending webhook notification for job {job_id}, trace_id: {trace_id} Connection Error: {repr(e)}")
    except aiohttp.ClientPayloadError as e:
        logger.error(f"Error sending webhook notification for job {job_id}, trace_id: {trace_id} Payload Error: {repr(e)}")
    except Exception as e:
        logger.error(f"Error sending webhook notification for job {job_id}, trace_id: {trace_id} An unexpected error occurred: {repr(e)}")


async def process_job(job_id: str, trace_id: str = None):
    """
    Process a job.
    
    Args:
        job_id: Job ID
        trace_id: Trace ID (optional)
    """
    # Generate a new trace ID if not provided
    if trace_id is None:
        trace_id = generate_id()
        
    try:
        logger.info(
            f"Processing job {job_id}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        # Ensure Redis connection is active before processing
        await redis_client.connect_with_retry()  # Will retry indefinitely
        
        # Get job data
        job_data_json = await redis_client.get(f"job:{job_id}:data")
        job_type = await redis_client.get(f"job:{job_id}:type")
    
        if not job_data_json:
            raise Exception(f"Job data for job {job_id} not found")
            
        # Parse job data
        try:
            job_data = json.loads(job_data_json)
            
            # Log full job data for debugging
            logger.info(
                f"Job data: {job_data_json[:1000]}, job_id: {job_id}, trace_id: {trace_id}" 
            )
            
            # Process based on job type
            if job_type == JobType.SUBJECT_ANALYSIS.value:
                # For subject analysis
                subjects = job_data.get("subjects", [])
                min_confidence = job_data.get("min_confidence", None)
                
                if not subjects:
                    raise Exception("No subjects provided for analysis")
                
                results = await openai_service.analyze_subjects(subjects, min_confidence, job_id, trace_id)
            else:
                # For email analysis (default)
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
                
                results = await openai_service.analyze_email(job_data, job_id, trace_id)
                
        except json.JSONDecodeError:
            raise Exception(f"Invalid job data for job {job_id}")
        
        # Add job ID to results
        results["job_id"] = job_id
        
        # Store results
        await redis_client.setex(
            f"job:{job_id}:results",
            60 * 60 * 24 * 7,  # 7 day expiration
            json.dumps(results, cls=DateTimeEncoder)
        )
        
        # Update job status
        await redis_client.setex(
            f"job:{job_id}:status",
            60 * 60 * 24 * 7,  # 7 day expiration
            "completed"
        )
        
        # Get webhook URL - check job data first, then fall back to config
        webhook_url = config.get("webhook", {}).get("url")
        webhook_enabled = config.get("webhook", {}).get("enabled", False)
        # Send webhook notification if URL is available
        if webhook_enabled and webhook_url:

            webhook_timeout = config.get("webhook", {}).get("timeout", 10)
            webhook_url = webhook_url #+ job_type
            logger.info(
                f"Using webhook URL: {webhook_url} for job {job_id}, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}
            )

            await send_webhook_notification(webhook_url,webhook_timeout, results, job_id, trace_id)

        else:
            logger.info(
                f"No webhook URL found for job {job_id}, skipping notification, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}
            )

        logger.info(
            f"Job {job_id} completed successfully, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
    except Exception as e:
        logger.error(
            f"Error processing job {job_id}: {str(e)}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        
        # Update job status
        await redis_client.setex(
            f"job:{job_id}:status",
            60 * 60 * 24,  # 24 hour expiration
            "failed"
        )
        
        # Store error
        await redis_client.setex(
            f"job:{job_id}:error",
            60 * 60 * 24,  # 24 hour expiration
            str(e)
        )


async def poll_for_jobs():
    """Poll for pending jobs."""
    while True:
        try:
            # Ensure Redis connection is active
            try:
                await redis_client.ping()                
            except Exception as e:
                await redis_client.connect_with_retry()  # Retry indefinitely

            # Get pending jobs
            pending_jobs = await redis_client.keys("job:*:status")
            
            for job_key in pending_jobs:
                # Get job ID
                job_id = job_key.split(":")[1]
                
                # Get job status
                status = await redis_client.get(job_key)
                
                # Process pending jobs
                if status == "pending":
                    # Update job status to processing
                    await redis_client.setex(
                        f"job:{job_id}:status",
                        60 * 60 * 24,  # 24 hour expiration
                        "processing"
                    )
                    
                    # Process job with a new trace ID
                    asyncio.create_task(process_job(job_id, generate_id()))
            
            # Sleep for 1 second
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("Polling task cancelled, shutting down gracefully...")
                break
            
        except asyncio.CancelledError:
            logger.info("Polling task cancelled, shutting down gracefully...")
            break
        except Exception as e:
            logger.error(f"Error polling for jobs: {str(e)}")
            try:
                await asyncio.sleep(5)  # Reduced sleep time for faster recovery
            except asyncio.CancelledError:
                logger.info("Polling task cancelled during error recovery, shutting down gracefully...")
                break

async def main():
    """Main worker function."""
    try:
            
        env = config.get("app", {}).get("env", "development")
        version = config.get("app", {}).get("version", "0.1.0")
        logger.info(
            f"Mail Analysis Worker started - Environment: {env}, Version: {version}"
        )
        
        # Start polling for jobs
        await poll_for_jobs()

    except asyncio.CancelledError:
        logger.info("Worker cancelled, shutting down gracefully...")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down gracefully...")
    except Exception as e:
        logger.error(f"Unexpected error in worker: {str(e)}")
        raise
    finally:
        # Ensure Redis connection is closed
        await redis_client.disconnect()
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    """Run the worker."""
    # Run the worker
    asyncio.run(main())
