#!/usr/bin/env python3
"""
Redis client module for the Mail Analysis API.
"""

from redis import asyncio as redis
from loguru import logger

from app.core.config import config


class RedisClient:
    """Redis client wrapper."""
    
    def __init__(self):
        """Initialize Redis client."""
        self.client = None
        self.config = config.get("redis", {})
        
    async def connect(self):
        """Connect to Redis."""
        if self.client is not None:
            return
            
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
                
            logger.info(f"Connected to Redis at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            raise
            
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client is not None:
            await self.client.close()
            self.client = None
            logger.info("Disconnected from Redis")
            
    async def get(self, key):
        """
        Get value from Redis.
        
        Args:
            key: Redis key
            
        Returns:
            Value or None if key doesn't exist
        """
        if self.client is None:
            await self.connect()
            
        return await self.client.get(key)
        
    async def set(self, key, value):
        """
        Set value in Redis.
        
        Args:
            key: Redis key
            value: Value to set
        """
        if self.client is None:
            await self.connect()
            
        await self.client.set(key, value)
        
    async def setex(self, key, seconds, value):
        """
        Set value in Redis with expiration.
        
        Args:
            key: Redis key
            seconds: Expiration time in seconds
            value: Value to set
        """
        if self.client is None:
            await self.connect()
            
        await self.client.setex(key, seconds, value)
        
    async def delete(self, key):
        """
        Delete key from Redis.
        
        Args:
            key: Redis key
        """
        if self.client is None:
            await self.connect()
            
        await self.client.delete(key)
        
    async def exists(self, key):
        """
        Check if key exists in Redis.
        
        Args:
            key: Redis key
            
        Returns:
            True if key exists, False otherwise
        """
        if self.client is None:
            await self.connect()
            
        return await self.client.exists(key)
        
    async def incr(self, key):
        """
        Increment value in Redis.
        
        Args:
            key: Redis key
            
        Returns:
            New value
        """
        if self.client is None:
            await self.connect()
            
        return await self.client.incr(key)
        
    async def incrby(self, key, amount):
        """
        Increment value in Redis by the given amount.
        
        Args:
            key: Redis key
            amount: Amount to increment by
            
        Returns:
            New value
        """
        if self.client is None:
            await self.connect()
            
        return await self.client.incrby(key, amount)
        
    async def incrbyfloat(self, key, amount):
        """
        Increment float value in Redis by the given amount.
        
        Args:
            key: Redis key
            amount: Float amount to increment by
            
        Returns:
            New value
        """
        if self.client is None:
            await self.connect()
            
        return await self.client.incrbyfloat(key, amount)
        
    async def ttl(self, key):
        """
        Get the time to live for a key in seconds.
        
        Args:
            key: Redis key
            
        Returns:
            TTL in seconds, -2 if key doesn't exist, -1 if key has no expiry
        """
        if self.client is None:
            await self.connect()
            
        return await self.client.ttl(key)
        
    async def expire(self, key, seconds):
        """
        Set expiration time for key.
        
        Args:
            key: Redis key
            seconds: Expiration time in seconds
        """
        if self.client is None:
            await self.connect()
            
        await self.client.expire(key, seconds)
        
    async def zadd(self, key, mapping):
        """
        Add members to sorted set.
        
        Args:
            key: Redis key
            mapping: Dictionary of score -> member
        """
        if self.client is None:
            await self.connect()
            
        await self.client.zadd(key, mapping)
        
    async def zremrangebyscore(self, key, min_score, max_score):
        """
        Remove members from sorted set by score.
        
        Args:
            key: Redis key
            min_score: Minimum score
            max_score: Maximum score
        """
        if self.client is None:
            await self.connect()
            
        await self.client.zremrangebyscore(key, min_score, max_score)
        
    async def zcard(self, key):
        """
        Get number of members in sorted set.
        
        Args:
            key: Redis key
            
        Returns:
            Number of members
        """
        if self.client is None:
            await self.connect()
            
        return await self.client.zcard(key)
        
    async def ping(self):
        """
        Ping Redis server.
        
        Returns:
            True if ping successful, False otherwise
        """
        if self.client is None:
            await self.connect()
            
        return await self.client.ping()
        
    async def keys(self, pattern):
        """
        Get keys matching pattern.
        
        Args:
            pattern: Pattern to match
            
        Returns:
            List of matching keys
        """
        if self.client is None:
            await self.connect()
            
        return await self.client.keys(pattern)
    
    async def store_job_data(self, job_id: str, client_id: str, data: str, job_type: str = None, expiration: int = 60 * 60 * 24):
        """
        Store job data in Redis.
        
        Args:
            job_id: Job ID
            client_id: Client ID
            data: Job data (JSON string)
            job_type: Job type (optional)
            expiration: Expiration time in seconds (default: 24 hours)
        """
        if self.client is None:
            await self.connect()
            
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
    
    def pipeline(self):
        """
        Create Redis pipeline.
        
        Returns:
            Redis pipeline
        """
        if self.client is None:
            raise RuntimeError("Redis client not connected")
            
        return self.client.pipeline()


# Global Redis client instance
redis_client = RedisClient()
