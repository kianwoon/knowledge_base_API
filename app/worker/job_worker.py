#!/usr/bin/env python3
"""
Job worker implementation for the Mail Analysis API.
"""

import json
import asyncio
from loguru import logger

from app.core.config import config
from app.core.snowflake import generate_id
from app.worker.interfaces import JobRepository, Notifier, JobFactory
from app.worker.repository import RedisJobRepository
from app.worker.notifier import DefaultNotifier
from app.worker.processors import DefaultJobFactory


class JobWorker:
    """
    Job worker that processes jobs from the queue.
    Following the Single Responsibility Principle by delegating specific tasks to specialized classes.
    """
    
    def __init__(
        self,
        repository: JobRepository = None,
        notifier: Notifier = None,
        job_factory: JobFactory = None
    ):
        """
        Initialize the job worker with dependencies.
        
        Args:
            repository: Job repository
            notifier:  notifier
            job_factory: Job factory
        """


        # Dependency injection for better testability
        self.repository = repository or RedisJobRepository()
        self.notifier = notifier or DefaultNotifier()
        self.job_factory = job_factory or DefaultJobFactory()
    
    async def connect(self) -> None:
        """
        Connect to required services.
        
        Establishes connections to the repository and notifier.
        """
        try:
            logger.info("Connecting to services...")
            
            # Connect to repository (Redis or other storage)
            await self.repository.connect_with_retry()
            logger.info("Repository connection established")
            
            # Connect to notifier if it has a connect method
            if hasattr(self.notifier, 'connect'):
                await self.notifier.connect()
                logger.info("Notifier connection established")
                
            logger.info("All service connections established")
        except Exception as e:
            logger.error(f"Error connecting to services: {str(e)}")
            raise
    
    async def process_job(self, job_id: str, trace_id: str = None, owner: str = None) -> None:
        """
        Process a job.
        
        Args:
            job_id: Job ID
            trace_id: Trace ID (optional)
            owner: Owner of the job (optional)
        """
        # Generate a new trace ID if not provided
        if trace_id is None:
            trace_id = generate_id()
            
        try:
            logger.info(
                f"Processing job {job_id}, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}
            )
            
            # Get job data
            job_data_json = await self.repository.get_job_data(job_id, owner)
            job_type = await self.repository.get_job_type(job_id, owner)
        
            if not job_data_json:
                raise Exception(f"Job data for job {job_id} not found")
                
            # Parse job data
            try:
                job_data = json.loads(job_data_json)            

                # Log full job data for debugging
                logger.info(
                    f"Job data: {job_data_json}, job_id: {job_id}, trace_id: {trace_id}"
                )
                
                # Get appropriate processor for job type
                processor = self.job_factory.get_processor(job_type)
                
                # Process job
                results = await processor.process(job_data, job_id, trace_id, owner)
                    
            except json.JSONDecodeError:
                raise Exception(f"Invalid job data for job {job_id}")
            
            # Add job ID to results
            # results["job_id"] = job_id
            # results["job_data"] = job_data

            # Store results
            await self.repository.store_job_results(job_id, results, owner)
            
            # Update job status
            await self.repository.update_job_status(job_id, "completed", owner)
            
            # Send webhook notification if enabled and URL is available
            await self.notifier.send_notification(
                    results,
                    job_id,
                    trace_id
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
            await self.repository.update_job_status(job_id, "failed", 60 * 60 * 24)
            
            # Store error
            await self.repository.store_job_error(job_id, str(e), 60 * 60 * 24)
    
    async def poll_for_jobs(self) -> None:
        """
        Poll for pending jobs and process them.
        """
        while True:
            try:
                # Ensure Redis connection is active
                try:
                    await self.repository.ping()                
                except Exception:
                    await self.repository.connect_with_retry()  # Retry connection

                # Get pending jobs
                pending_jobs = await self.repository.get_pending_jobs()
                
                for job_key in pending_jobs:
                    # Get job ID
                    job_id = job_key.split(":")[1]
                    owner = job_key.split(":")[2] # for qdrant collections

                    # Get job status
                    status = await self.repository.get_job_status(job_key,owner)
                    
                    # Process pending jobs
                    if status == "pending":
                        # Update job status to processing
                        await self.repository.update_job_status(job_id, "processing", owner, 60 * 60 * 24)
 
                        # Process job with a new trace ID
                        await self.process_job(job_id, generate_id(), owner)
                        # asyncio.create_task(self.process_job(job_id, generate_id(), owner))
                
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
    
    async def run(self) -> None:
        """
        Run the worker.
        """
        try:
            env = config.get("app", {}).get("env", "development")
            version = config.get("app", {}).get("version", "0.1.0")
            logger.info(
                f"Mail Analysis Worker started - Environment: {env}, Version: {version}"
            )
            await self.connect()
            # Start polling for jobs
            await self.poll_for_jobs()

        except asyncio.CancelledError:
            logger.info("Worker cancelled, shutting down gracefully...")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down gracefully...")
        except Exception as e:
            logger.error(f"Unexpected error in worker: {str(e)}")
            raise
        finally:
            # Ensure Redis connection is closed
            await self.repository.disconnect()
            logger.info("Worker shutdown complete")