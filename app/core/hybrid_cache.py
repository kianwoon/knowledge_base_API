#!/usr/bin/env python3
"""
Hybrid cache implementation with Read-Through and Write-Through strategies.
"""

import asyncio
import json
from typing import List, Any

from loguru import logger

from app.core.interfaces import CacheInterface
from app.core.redis import redis_client, RedisCache
from app.core.postgres_cache import postgres_client, PostgresCache


class HybridCache(CacheInterface):
    """
    Hybrid cache implementation with Read-Through and Write-Through strategies.
    
    This class uses Redis as the primary cache and PostgreSQL as the persistence layer.
    It implements:
    - Read-Through: Data is fetched from PostgreSQL if not found in Redis
    - Write-Through: Data is written to both Redis and PostgreSQL
    """
    
    def __init__(
        self, 
        redis_cache: RedisCache = None, 
        postgres_cache: PostgresCache = None
    ):
        """Initialize hybrid cache.
        
        Args:
            redis_cache: Redis cache implementation
            postgres_cache: PostgreSQL cache implementation
        """
        self.redis = redis_cache or redis_client
        self.postgres = postgres_cache or postgres_client
    
    async def connect(self) -> None:
        """Connect to both caches."""
        await self.redis.connect()
        await self.postgres.connect()
    
    async def disconnect(self) -> None:
        """Disconnect from both caches."""
        await self.redis.disconnect()
        await self.postgres.disconnect()
    
    async def connect_with_retry(self) -> None:
        """Connect to the caches with retry mechanism."""
        await self.redis.connect_with_retry()
        await self.postgres.connect()
    
    async def get(self, key: str) -> Any:
        """
        Get value from cache using Read-Through strategy.
        
        First tries Redis, if not found, falls back to PostgreSQL
        and updates Redis if found in PostgreSQL.
        
        Args:
            key: Cache key
            
        Returns:
            Value or None if key doesn't exist
        """
        # First try Redis (fast)
        value = await self.redis.get(key)
        
        if value is None:
            # Cache miss: try the persistent PostgreSQL store
            logger.debug(f"Cache miss for key '{key}', trying PostgreSQL")
            value = await self.postgres.get(key)
            
            if value is not None:
                # Found in PostgreSQL, repopulate Redis cache (asynchronously)
                logger.debug(f"Found key '{key}' in PostgreSQL, updating Redis")
                # Get TTL from PostgreSQL or use default
                ttl = 3600  # 1 hour default
                asyncio.create_task(self.redis.setex(key, ttl, value))
        
        return value
    
    async def set(self, key: str, value: Any) -> None:
        """
        Set value in cache using Write-Through strategy.
        
        Writes to both Redis and PostgreSQL.
        
        Args:
            key: Cache key
            value: Value to set
        """
        # Write to both caches
        await asyncio.gather(
            self.redis.set(key, value),
            self.postgres.set(key, value)
        )
    
    async def setex(self, key: str, seconds: int, value: Any) -> None:
        """
        Set value in cache with expiration using Write-Through strategy.
        
        Writes to both Redis and PostgreSQL with the same expiration.
        
        Args:
            key: Cache key
            seconds: Expiration time in seconds
            value: Value to set
        """
        # Write to both caches
        await asyncio.gather(
            self.redis.setex(key, seconds, value),
            self.postgres.setex(key, seconds, value)
        )
    
    async def delete(self, key: str) -> None:
        """
        Delete key from both caches.
        
        Args:
            key: Cache key
        """
        # Delete from both caches
        await asyncio.gather(
            self.redis.delete(key),
            self.postgres.delete(key)
        )
    
    async def keys(self, pattern: str) -> List[str]:
        """
        Get keys matching pattern from Redis first, falling back to PostgreSQL.
        
        Args:
            pattern: Pattern to match
            
        Returns:
            List of matching keys
        """
        try:
            # Try Redis first
            keys = await self.redis.keys(pattern)
            if keys:
                return keys
            
            # Fall back to PostgreSQL
            return await self.postgres.keys(pattern)
        except Exception as e:
            logger.error(f"Error getting keys with pattern '{pattern}': {str(e)}")
            return []
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Checks Redis first, then PostgreSQL if not found.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        # Check Redis first
        redis_exists = await self.redis.exists(key)
        if redis_exists:
            return True
        
        # Fall back to PostgreSQL
        value = await self.postgres.get(key)
        return value is not None
    
    # Forward the remaining methods to Redis
    async def incr(self, key: str) -> int:
        value = await self.redis.incr(key)
        # Update PostgreSQL asynchronously
        asyncio.create_task(self.postgres.set(key, str(value)))
        return value
    
    async def incrby(self, key: str, amount: int) -> int:
        value = await self.redis.incrby(key, amount)
        # Update PostgreSQL asynchronously
        asyncio.create_task(self.postgres.set(key, str(value)))
        return value
    
    async def incrbyfloat(self, key: str, amount: float) -> float:
        value = await self.redis.incrbyfloat(key, amount)
        # Update PostgreSQL asynchronously
        asyncio.create_task(self.postgres.set(key, str(value)))
        return value
    
    async def eval(self, script: str, keys: List[str], args: List[Any]) -> Any:
        # This is specific to Redis, no direct PostgreSQL equivalent
        return await self.redis.eval(script, keys, args)
    
    # Add additional helper methods as needed
    async def store_job_data(self, job_id: str, client_id: str, data: str, job_type: str = None, expiration: int = 60 * 60 * 24) -> None:
        """
        Store job data using Write-Through strategy.
        
        Args:
            job_id: Job ID
            client_id: Client ID
            data: Job data (JSON string)
            job_type: Job type (optional)
            expiration: Expiration time in seconds (default: 24 hours)
        """
        # Use existing Redis implementation, but also persist to PostgreSQL
        # Store job status
        await self.setex(
            f"job:{job_id}:status",
            expiration,
            "pending"
        )
        
        # Store client ID for job
        await self.setex(
            f"job:{job_id}:client",
            expiration,
            client_id
        )
        
        # Store job data
        await self.setex(
            f"job:{job_id}:data",
            expiration,
            data
        )
        
        # Store job type if provided
        if job_type:
            await self.setex(
                f"job:{job_id}:type",
                expiration,
                job_type
            )
    
    async def expire(self, key: str, seconds: int) -> None:
        """
        Set expiration time on key.
        
        Sets expiration in both Redis and PostgreSQL.
        
        Args:
            key: Cache key
            seconds: Expiration time in seconds
        """
        # Set expiration in both caches
        await asyncio.gather(
            self.redis.expire(key, seconds),
            self.postgres.expire(key, seconds)
        )

    async def ttl(self, key: str) -> int:
        """
        Get time to live for a key.
        
        Gets TTL from Redis first, falls back to PostgreSQL if not found.
        
        Args:
            key: Cache key
            
        Returns:
            TTL in seconds, -2 if key doesn't exist, -1 if no expiry
        """
        # Try Redis first
        ttl = await self.redis.ttl(key)
        
        # If key doesn't exist in Redis, check PostgreSQL
        if ttl == -2:  # -2 means key doesn't exist
            exists = await self.postgres.exists(key)
            if exists:
                # If it exists in PostgreSQL but not Redis, get value and TTL from PostgreSQL
                ttl = await self.postgres.ttl(key)
                
                # Populate Redis cache if found in PostgreSQL
                if ttl != -2:  # Key exists in PostgreSQL
                    value = await self.postgres.get(key)
                    if value is not None:
                        # Only set in Redis if there's a TTL, otherwise use default
                        if ttl > 0:
                            asyncio.create_task(self.redis.setex(key, ttl, value))
                        else:
                            asyncio.create_task(self.redis.set(key, value))
        
        return ttl

    async def zadd(self, key: str, mapping: dict) -> int:
        """
        Add one or more members to a sorted set, or update their scores if they already exist.
        
        This is primarily a Redis operation, but we also store a version in PostgreSQL for redundancy.
        
        Args:
            key: Sorted set key
            mapping: Dictionary mapping member names to scores
            
        Returns:
            Number of elements added to the sorted set
        """
        # Execute in Redis
        result = await self.redis.zadd(key, mapping)
        
        # Store in PostgreSQL as well (as a serialized JSON or similar format)
        # This is a simplified implementation and might need refinement
        # based on how exactly you want to handle sorted sets in PostgreSQL
        try:
            # Get existing set from PostgreSQL if it exists
            existing_data = await self.postgres.get(key)
            if existing_data:
                try:
                    existing_mapping = json.loads(existing_data)
                except:
                    existing_mapping = {}
            else:
                existing_mapping = {}
                
            # Update with new values
            existing_mapping.update(mapping)
            
            # Store updated mapping back to PostgreSQL
            await self.postgres.set(key, json.dumps(existing_mapping))
        except Exception as e:
            logger.error(f"Error storing sorted set in PostgreSQL: {str(e)}")
        
        return result

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        """
        Remove all elements in a sorted set with scores between min and max.
        
        This is primarily a Redis operation, but we also maintain the state in PostgreSQL for redundancy.
        
        Args:
            key: Sorted set key
            min_score: Minimum score (inclusive)
            max_score: Maximum score (inclusive)
            
        Returns:
            Number of elements removed
        """
        # Execute in Redis
        result = await self.redis.zremrangebyscore(key, min_score, max_score)
        
        # Update in PostgreSQL as well
        try:
            # Get existing set from PostgreSQL if it exists
            existing_data = await self.postgres.get(key)
            if existing_data:
                try:
                    existing_mapping = json.loads(existing_data)
                    if existing_mapping:
                        # Remove elements with scores between min and max
                        updated_mapping = {
                            member: score 
                            for member, score in existing_mapping.items() 
                            if not (min_score <= float(score) <= max_score)
                        }
                        
                        # Store updated mapping back to PostgreSQL
                        await self.postgres.set(key, json.dumps(updated_mapping))
                except Exception as e:
                    logger.error(f"Error updating sorted set in PostgreSQL after zremrangebyscore: {str(e)}")
        except Exception as e:
            logger.error(f"Error handling zremrangebyscore in PostgreSQL: {str(e)}")
        
        return result

    async def zcard(self, key: str) -> int:
        """
        Get the number of members in a sorted set.
        
        This is primarily a Redis operation, but we maintain compatibility with our PostgreSQL backup.
        
        Args:
            key: Sorted set key
            
        Returns:
            Number of elements in the sorted set
        """
        # Try Redis first
        result = await self.redis.zcard(key)
        
        # If key doesn't exist in Redis but might exist in PostgreSQL
        if result == 0:
            try:
                # Get existing set from PostgreSQL if it exists
                existing_data = await self.postgres.get(key)
                if existing_data:
                    try:
                        # Parse the JSON representation of the sorted set
                        existing_mapping = json.loads(existing_data)
                        # Return the number of members in the mapping
                        return len(existing_mapping)
                    except Exception as e:
                        logger.error(f"Error parsing sorted set data from PostgreSQL: {str(e)}")
            except Exception as e:
                logger.error(f"Error getting zcard from PostgreSQL: {str(e)}")
        
        return result

    async def ping(self) -> bool:
        """
        Check if cache is responsive.
        
        Checks Redis first, then PostgreSQL if Redis fails.
        
        Returns:
            True if either cache responds to ping, False if both fail
        """
        try:
            # Try Redis first
            redis_result = await self.redis.ping()
            if redis_result:
                return True
                
            # Fall back to PostgreSQL if Redis fails
            postgres_result = await self.postgres.ping()
            return postgres_result
        except Exception as e:
            logger.error(f"Error pinging caches: {str(e)}")
            return False
 
# Global hybrid cache instance
hybrid_cache = HybridCache()