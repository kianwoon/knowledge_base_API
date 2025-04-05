#!/usr/bin/env python3
"""
Cache implementation module for the Mail Analysis API.
"""

from redis import asyncio as redis
from loguru import logger
import asyncio
from typing import Dict, List, Any, Union

from app.core.config import config
from app.core.interfaces import CacheInterface


class RedisConnectionManager:
    """Redis connection manager."""
    
    def __init__(self):
        """Initialize Redis connection manager."""
        self.client = None
        self.config = config.get("redis", {})
    
    async def connect(self) -> redis.Redis:
        """Connect to Redis.
        
        Returns:
            Redis client
        """
        if self.client is not None:
            return self.client
            
        host = self.config.get("host", "localhost")
        port = self.config.get("port", 6379)
        password = self.config.get("password")
        
        try:
            self.client = redis.Redis(
                host=host,
                port=port,
                password=password,
                encoding="utf-8",
                decode_responses=True
            )
            await self.client.ping()    
            logger.info(f"Connected to Redis at {host}:{port}")
            return self.client
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.client is not None:
            await self.client.close()
            self.client = None
            logger.info("Disconnected from Redis")
    
    async def connect_with_retry(self, initial_retry_delay: int = 30, max_retry_delay: int = 600) -> bool:
        """Connect to Redis with retry mechanism that never gives up.
        
        Args:
            initial_retry_delay: Initial delay between retries in seconds (default: 30s)
            max_retry_delay: Maximum delay between retries in seconds (default: 10 minutes)
            
        Returns:
            True when connection is successful (will retry indefinitely until success)
        """
        retries = 0
        current_delay = initial_retry_delay
        
        while True:  # Infinite loop - will always retry
            try:
                retries += 1
                # logger.info(f"Attempting to connect to Redis (attempt {retries})...")
                # Test connection with ping
                await self.connect()
                if self.client and await self.client.ping():
                    # logger.info("Successfully connected to Redis")
                    return True
                else:
                    logger.warning("Redis connection established but ping failed")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {str(e)}")
            
            # Wait before retrying with exponential backoff (capped at max_retry_delay)
            logger.info(f"Waiting {current_delay} seconds before retrying...")
            await asyncio.sleep(current_delay)
            
            # Increase delay for next retry (exponential backoff with cap)
            current_delay = min(current_delay * 1.5, max_retry_delay)


class RedisCache(CacheInterface):
    """Redis cache implementation."""
    
    def __init__(self, connection_manager: RedisConnectionManager = None):
        """Initialize Redis cache.
        
        Args:
            connection_manager: Redis connection manager (optional)
        """
        self.connection_manager = connection_manager or RedisConnectionManager()
    
    async def connect(self) -> None:
        """Connect to the cache."""
        await self.connection_manager.connect()
    
    async def disconnect(self) -> None:
        """Disconnect from the cache."""
        await self.connection_manager.disconnect()

    async def scan(self, pattern: str) -> List[str]:
        """Scan for keys matching pattern.
        
        Args:
            pattern: Pattern to match
            
        Returns:
            List of matching keys
        """
        client = await self.connection_manager.connect()
        cursor = "0"
        keys = []
        
        while cursor != 0:
            cursor, partial_keys = await client.scan(cursor, match=pattern)
            keys.extend(partial_keys)
        
        return keys
    
    

    async def connect_with_retry(self) -> None:
        """Connect to the cache with retry mechanism."""
        await self.connection_manager.connect_with_retry()

    async def get(self, key: str) -> Any:
        """Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Value or None if key doesn't exist
        """
        client = await self.connection_manager.connect()
        return await client.get(key)
    async def eval(self, script: str, keys: List[str], args: List[Any]) -> Any:
        """Evaluate Lua script in Redis.
        
        Args:
            script: Lua script
            keys: List of keys to pass to the script
            args: List of arguments to pass to the script
        """
        client = await self.connection_manager.connect()
        return await client.eval(script, keys, args) 

           
    async def set(self, key: str, value: Any) -> None:
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to set
        """
        client = await self.connection_manager.connect()
        await client.set(key, value)
    
    async def setex(self, key: str, seconds: int, value: Any) -> None:
        """Set value in cache with expiration.
        
        Args:
            key: Cache key
            seconds: Expiration time in seconds
            value: Value to set
        """
        client = await self.connection_manager.connect()
        await client.setex(key, seconds, value)
    
    async def delete(self, key: str) -> None:
        """Delete key from cache.
        
        Args:
            key: Cache key
        """
        client = await self.connection_manager.connect()
        await client.delete(key)
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        client = await self.connection_manager.connect()
        return bool(await client.exists(key))
    
    async def incr(self, key: str) -> int:
        """Increment value in cache.
        
        Args:
            key: Cache key
            
        Returns:
            New value
        """
        client = await self.connection_manager.connect()
        return await client.incr(key)
    
    async def incrby(self, key: str, amount: int) -> int:
        """Increment value in cache by amount.
        
        Args:
            key: Cache key
            amount: Amount to increment by
            
        Returns:
            New value
        """
        client = await self.connection_manager.connect()
        return await client.incrby(key, amount)
    
    async def incrbyfloat(self, key: str, amount: float) -> float:
        """Increment float value in cache by amount.
        
        Args:
            key: Cache key
            amount: Amount to increment by
            
        Returns:
            New value
        """
        client = await self.connection_manager.connect()
        return await client.incrbyfloat(key, amount)
    
    async def ttl(self, key: str) -> int:
        """Get time to live for key.
        
        Args:
            key: Cache key
            
        Returns:
            TTL in seconds, -2 if key doesn't exist, -1 if key has no expiry
        """
        client = await self.connection_manager.connect()
        return await client.ttl(key)
    
    async def expire(self, key: str, seconds: int) -> None:
        """Set expiration time for key.
        
        Args:
            key: Cache key
            seconds: Expiration time in seconds
        """
        client = await self.connection_manager.connect()
        await client.expire(key, seconds)
    
    # Additional Redis-specific methods that extend the base interface
    async def zadd(self, key: str, mapping: Dict[str, Union[int, float]]) -> None:
        """Add members to sorted set.
        
        Args:
            key: Redis key
            mapping: Dictionary of score -> member
        """
        client = await self.connection_manager.connect()
        await client.zadd(key, mapping)
    
    async def zremrangebyscore(self, key: str, min_score: Union[int, float], max_score: Union[int, float]) -> None:
        """Remove members from sorted set by score.
        
        Args:
            key: Redis key
            min_score: Minimum score
            max_score: Maximum score
        """
        client = await self.connection_manager.connect()
        await client.zremrangebyscore(key, min_score, max_score)
    
    async def zcard(self, key: str) -> int:
        """Get number of members in sorted set.
        
        Args:
            key: Redis key
            
        Returns:
            Number of members
        """
        client = await self.connection_manager.connect()
        return await client.zcard(key)
    
    async def keys(self, pattern: str) -> List[str]:
        """Get keys matching pattern.
        
        Args:
            pattern: Pattern to match
            
        Returns:
            List of matching keys
        """
        client = await self.connection_manager.connect()
        return await client.keys(pattern)
    
    def pipeline(self):
        """Create Redis pipeline.
        
        Returns:
            Redis pipeline
            
        Raises:
            RuntimeError: If Redis client not connected
        """
        if self.connection_manager.client is None:
            raise RuntimeError("Redis client not connected")
        
        return self.connection_manager.client.pipeline()
    
    async def store_job_data(self, job_id: str, client_id: str, data: str, job_type: str = None, expiration: int = 60 * 60 * 24) -> None:
        """Store job data in Redis.
        
        Args:
            job_id: Job ID
            client_id: Client ID
            data: Job data (JSON string)
            job_type: Job type (optional)
            expiration: Expiration time in seconds (default: 24 hours)
        """
        await self.connection_manager.connect()
        
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
    #        
    async def register_script(self, script_name: str, script_content: str) -> None:
        """Register a Lua script in Redis.
        
        Args:
            script_name: Name of the script
            script_content: Lua script content
        """
        client = await self.connection_manager.connect()
        await client.script_load(script_content)
        await client.set(f"script:{script_name}", script_content)
        


# Global Redis cache instance
redis_client = RedisCache()