#!/usr/bin/env python3
"""
Repository implementations for the Worker module.
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from app.core.redis import redis_client
from app.worker.interfaces import JobRepository
from app.core.config import localize_datetime


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    
    def default(self, obj):
        if isinstance(obj, datetime):
            # Ensure datetime has timezone info before converting to ISO format
            if obj.tzinfo is None:
                obj = localize_datetime(obj)
            return obj.isoformat()
        return super().default(obj)


class RedisJobRepository(JobRepository):
    """Redis implementation of the JobRepository interface."""
    
    async def get_job_data(self, job_id: str) -> Optional[str]:
        """
        Get job data from Redis.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job data as JSON string or None if not found
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect_with_retry()
            return await redis_client.get(f"job:{job_id}:data")
        except Exception as e:
            logger.error(f"Error getting job data for job {job_id}: {str(e)}")
            return None
    
    async def get_job_type(self, job_id: str) -> Optional[str]:
        """
        Get job type from Redis.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job type or None if not found
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect_with_retry()
            return await redis_client.get(f"job:{job_id}:type")
        except Exception as e:
            logger.error(f"Error getting job type for job {job_id}: {str(e)}")
            return None
    
    async def store_job_results(self, job_id: str, results: Dict[str, Any], expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Store job results in Redis.
        
        Args:
            job_id: Job ID
            results: Job results
            expiration: Expiration time in seconds (default: 7 days)
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect_with_retry()
            await redis_client.setex(
                f"job:{job_id}:results",
                expiration,
                json.dumps(results, cls=DateTimeEncoder)
            )
        except Exception as e:
            logger.error(f"Error storing job results for job {job_id}: {str(e)}")
            raise
    
    async def update_job_status(self, job_id: str, status: str, expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Update job status in Redis.
        
        Args:
            job_id: Job ID
            status: Job status
            expiration: Expiration time in seconds (default: 7 days)
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect_with_retry()
            await redis_client.setex(
                f"job:{job_id}:status",
                expiration,
                status
            )
        except Exception as e:
            logger.error(f"Error updating job status for job {job_id}: {str(e)}")
            raise
    
    async def store_job_error(self, job_id: str, error: str, expiration: int = 60 * 60 * 24) -> None:
        """
        Store job error in Redis.
        
        Args:
            job_id: Job ID
            error: Error message
            expiration: Expiration time in seconds (default: 24 hours)
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect()
            await redis_client.setex(
                f"job:{job_id}:error",
                expiration,
                error
            )
        except Exception as e:
            logger.error(f"Error storing job error for job {job_id}: {str(e)}")
            raise
    
    async def get_pending_jobs(self) -> List[str]:
        """
        Get pending jobs from Redis.
        
        Returns:
            List of pending job keys
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect()
            return await redis_client.scan("job:*:status")
        except Exception as e:
            logger.error(f"Error getting pending jobs: {str(e)}")
            return []

    async def get_pending_jobs_lua(self) -> List[str]:
        """
        Get pending jobs from Redis using Lua script.
        
        Returns:
            List of pending job keys
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect()
            script = """
                local cursor = "0"
                local pending_jobs = {}
                repeat
                    local result = redis.call('scan', cursor, 'match', 'job:*:status')
                    cursor = result[1]
                    local keys = result[2]
                    for i = 1, #keys do
                        local key = keys[i]
                        if redis.call('get', key) == 'pending' then
                            table.insert(pending_jobs, key)
                        end
                    end
                until cursor == "0"
                return pending_jobs
            """
            return await redis_client.eval(script,keys=[], args=[])
        except Exception as e:
            logger.error(f"Error getting pending jobs with Lua script: {str(e)}")
            return []

    async def get_job_status(self, job_key: str) -> Optional[str]:
        """
        Get job status from Redis.
        
        Args:
            job_key: Job key
            
        Returns:
            Job status or None if not found
        """
        try:
            return await redis_client.get(job_key)
        except Exception as e:
            logger.error(f"Error getting job status for key {job_key}: {str(e)}")
            return None