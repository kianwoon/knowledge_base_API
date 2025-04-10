#!/usr/bin/env python3
"""
Worker module for the Mail Analysis API.

This module serves as the entry point for the worker process.
It uses the SOLID-based implementation in job_worker.py.
"""

import asyncio
from loguru import logger

from app.worker.job_worker import JobWorker
from app.worker.repository_redis import RedisJobRepository
from app.worker.notifier import DefaultWebhookNotifier
from app.worker.processors import DefaultJobFactory

async def main():
    """
    Main worker function.
    Creates and runs JobWorker instances with the default implementations.
    """
    try:

        logger.info("Starting Redis worker...")


        # Create redis worker with dependencies
        redis_worker = JobWorker(
            repository=RedisJobRepository(),
            notifier=DefaultWebhookNotifier(),
            job_factory=DefaultJobFactory()
        )
        
        # Run redis worker
        await redis_worker.run()
        
    except Exception as e:
        logger.error(f"Unexpected error in worker main function: {str(e)}")
        raise


if __name__ == "__main__":
    """
    Run the worker.
    """
    # Run the worker
    asyncio.run(main())
