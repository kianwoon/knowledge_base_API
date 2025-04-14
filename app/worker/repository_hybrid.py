#!/usr/bin/env python3
"""Repository implementations for the Worker module using Hybrid Cache."""

import json
from typing import Dict, Any, Optional, List
from loguru import logger

from app.core.hybrid_cache import hybrid_cache
from app.worker.interfaces import JobRepository
from app.worker.repository_redis import DateTimeEncoder


class HybridJobRepository(JobRepository):
    """Hybrid cache implementation of the JobRepository interface."""
    
    async def ping(self) -> None:
        """Ping the cache to check connectivity."""
        try:
            await hybrid_cache.connect()
        except Exception as e:
            logger.error(f"Error pinging cache: {str(e)}")
            raise
    
    async def connect_with_retry(self) -> None:
        """Connect to cache with retry logic."""
        try:
            await hybrid_cache.connect_with_retry()
        except Exception as e:
            logger.error(f"Error connecting to cache: {str(e)}")
            raise
    
    async def get_job_data(self, job_id: str, owner: str = None) -> Optional[str]:
        """
        Get job data from cache.
        
        Args:
            job_id: Job ID
            owner: Optional owner for authorization check
            
        Returns:
            Job data as JSON string or None if not found
        """
        try:
            # Ensure cache connection is active
            await hybrid_cache.connect_with_retry()
            return await hybrid_cache.get(f"job:{job_id}:data")
        except Exception as e:
            logger.error(f"Error getting job data for job {job_id}: {str(e)}")
            return None
    
    async def get_job_type(self, job_id: str, owner: str = None) -> Optional[str]:
        """
        Get job type from cache.
        
        Args:
            job_id: Job ID
            owner: Optional owner for authorization check
            
        Returns:
            Job type or None if not found
        """
        try:
            # Ensure cache connection is active
            await hybrid_cache.connect_with_retry()
            return await hybrid_cache.get(f"job:{job_id}:type")
        except Exception as e:
            logger.error(f"Error getting job type for job {job_id}: {str(e)}")
            return None
    
    async def store_job_results(self, job_id: str, results: Dict[str, Any], owner: str = None, expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Store job results in cache.
        
        Args:
            job_id: Job ID
            results: Job results
            owner: Optional owner for authorization check
            expiration: Expiration time in seconds (default: 7 days)
        """
        try:
            # Ensure cache connection is active
            await hybrid_cache.connect_with_retry()
            await hybrid_cache.setex(
                f"job:{job_id}:results",
                expiration,
                json.dumps(results, cls=DateTimeEncoder)
            )
        except Exception as e:
            logger.error(f"Error storing job results for job {job_id}: {str(e)}")
            raise
    
    async def update_job_status(self, job_id: str, status: str, owner: str = None, expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Update job status in cache.
        
        Args:
            job_id: Job ID
            status: Job status
            owner: Optional owner for authorization check
            expiration: Expiration time in seconds (default: 7 days)
        """
        try:
            # Ensure cache connection is active
            await hybrid_cache.connect_with_retry()
            await hybrid_cache.setex(
                f"job:{job_id}:status",
                expiration,
                status
            )
        except Exception as e:
            logger.error(f"Error updating job status for job {job_id}: {str(e)}")
            raise
    
    async def store_job_error(self, job_id: str, error: str, expiration: int = 60 * 60 * 24) -> None:
        """
        Store job error in cache.
        
        Args:
            job_id: Job ID
            error: Error message
            expiration: Expiration time in seconds (default: 24 hours)
        """
        try:
            # Ensure cache connection is active
            await hybrid_cache.connect()
            await hybrid_cache.setex(
                f"job:{job_id}:error",
                expiration,
                error
            )
        except Exception as e:
            logger.error(f"Error storing job error for job {job_id}: {str(e)}")
            raise
    
    async def get_job_id(self, job_key):
        """Extract job ID from job key."""
        return job_key.split(":")[1] if ":" in job_key else job_key
    
    async def get_pending_jobs(self) -> List[str]:
        """
        Get pending jobs from cache.
        
        Returns:
            List of pending job keys
        """
        try:
            # Ensure cache connection is active
            await hybrid_cache.connect()
            return await hybrid_cache.scan("job:*:status")
        except Exception as e:
            logger.error(f"Error getting pending jobs: {str(e)}")
            return []
    
    async def get_pending_jobs_lua(self) -> List[str]:
        """
        Get pending jobs from cache using Lua script with limits.
        
        Returns:
            List of pending job keys (limited to prevent memory issues)
        """
        try:
            # Ensure cache connection is active
            await hybrid_cache.connect()
            script = """
                local cursor = "0"
                local pending_jobs = {}
                local max_jobs = 100  -- Limit number of jobs to process at once
                local count = 0
                
                repeat
                    local result = redis.call('scan', cursor, 'MATCH', 'job:*:status', 'COUNT', 50)
                    cursor = result[1]
                    local keys = result[2]
                    for i = 1, #keys do
                        if count >= max_jobs then
                            break
                        end
                        local key = keys[i]
                        if redis.call('get', key) == 'pending' then
                            table.insert(pending_jobs, key)
                            count = count + 1
                        end
                    end
                until cursor == "0" or count >= max_jobs
                return pending_jobs
            """
            return await hybrid_cache.eval(script, keys=[], args=[])
        except Exception as e:
            logger.error(f"Error getting pending jobs with Lua script: {str(e)}")
            return []
    
    async def get_job_status(self, job_key: str, owner: str = None) -> Optional[str]:
        """
        Get job status from cache.
        
        Args:
            job_key: Job key
            owner: Optional owner for authorization check
            
        Returns:
            Job status or None if not found
        """
        try:
            # Ensure cache connection is active
            await hybrid_cache.connect()
            return await hybrid_cache.get(job_key)
        except Exception as e:
            logger.error(f"Error getting job status for key {job_key}: {str(e)}")
            return None