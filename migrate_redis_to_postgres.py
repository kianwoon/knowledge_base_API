#!/usr/bin/env python3
"""
Script to migrate data from Redis to PostgreSQL.
This is a one-time migration to initialize the PostgreSQL database with existing Redis data.
"""

import asyncio
import os
from loguru import logger


async def migrate_keys(pattern: str, expiration_days: int = 7) -> None:
    """
    Migrate keys matching pattern from Redis to PostgreSQL.
    
    Args:
        pattern: Redis key pattern to match
        expiration_days: Default expiration in days for keys without TTL
    """
    from app.core.redis import redis_client
    from app.core.postgres_cache import postgres_client
    
    try:
        # Connect to Redis and PostgreSQL
        await redis_client.connect()
        await postgres_client.connect()
        
        # Get all matching keys
        keys = await redis_client.keys(pattern)
        logger.info(f"Found {len(keys)} keys matching pattern '{pattern}'")
        
        # Process each key
        for key in keys:
            # Handle both bytes and string keys
            key_str = key if isinstance(key, str) else key.decode()
            
            # Get value and TTL from Redis
            value = await redis_client.get(key_str)
            ttl = await redis_client.ttl(key_str)
            
            if value is not None:
                # Handle both bytes and string values
                value_str = value if isinstance(value, str) else value.decode()
                
                # Calculate expiration (use TTL from Redis if available)
                if ttl > 0:
                    seconds = ttl
                else:
                    # Default expiration if TTL is -1 (no expiration) or -2 (key not found)
                    seconds = expiration_days * 24 * 60 * 60
                
                # Store in PostgreSQL
                await postgres_client.setex(key_str, seconds, value_str)
                logger.info(f"Migrated key: {key_str}")
    
    except Exception as e:
        logger.error(f"Error migrating keys with pattern '{pattern}': {str(e)}")
        # Raise the exception again to handle it at the caller level
        raise
    
    finally:
        # Disconnect from both databases
        try:
            await redis_client.disconnect()
        except Exception:
            pass
            
        try:
            await postgres_client.disconnect()
        except Exception:
            pass


async def main() -> None:
    """Main migration function."""
    logger.info("Starting Redis to PostgreSQL migration")
    
    try:
        # Migrate API keys (1 year expiration if not set)
        await migrate_keys("api_keys:*", expiration_days=365)
        
        # # Migrate job data
        # await migrate_keys("job:*:data", expiration_days=7)
        # await migrate_keys("job:*:status", expiration_days=7)
        # await migrate_keys("job:*:results", expiration_days=7)
        # await migrate_keys("job:*:type", expiration_days=7)
        # await migrate_keys("job:*:client", expiration_days=7)
        # await migrate_keys("job:*:error", expiration_days=1)
        
        # Add more patterns as needed
        
        logger.info("Migration completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        exit(1)


if __name__ == "__main__":
    """Run the migration script."""
    # Validate that DATABASE_URL is available
    if not os.environ.get("DATABASE_URL"):
        # Try to load from settings if possible
        try:
            from app.core.config import config
            database_url = config.get("postgres", {}).get("database_url")
            if database_url:
                os.environ["DATABASE_URL"] = database_url
                logger.info("Using database URL from config")
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
    
    if not os.environ.get("DATABASE_URL"):
        logger.error("DATABASE_URL environment variable is required")
        logger.info("Please set DATABASE_URL=postgres://user:password@host:port/dbname")
        exit(1)
        
    asyncio.run(main())