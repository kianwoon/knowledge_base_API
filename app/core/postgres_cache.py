#!/usr/bin/env python3
"""
PostgreSQL persistence layer for the Mail Analysis API cache.
"""

from datetime import datetime, timedelta
from typing import List, Any, Optional

import asyncpg
from loguru import logger

from app.core.config import get_settings 


class PostgresConnection:
    """PostgreSQL connection manager."""
    
    def __init__(self, min_size=2, max_size=10):
        """
        Initialize PostgreSQL connection manager.
        
        Args:
            min_size: Minimum number of connections in the pool (default: 2)
            max_size: Maximum number of connections in the pool (default: 10)
        """
        self.pool = None
        self.settings = get_settings()
        self.min_size = min_size
        self.max_size = max_size
    
    async def connect(self) -> asyncpg.Pool:
        """Connect to PostgreSQL.
        
        Returns:
            PostgreSQL connection pool
        """
        if self.pool is not None and not self.pool._closed:
            return self.pool
            
        # Try to get the database_url from environment variables first
        import os
        database_url = os.environ.get("DATABASE_URL")
        
        # If not in environment variables, try to get from settings object
        if not database_url:
            try:
                # Try to access as attribute first (Pydantic model)
                database_url = getattr(self.settings, "database_url", None)
            except (AttributeError, TypeError):
                pass
                
            # If not found as attribute, try as dictionary key
            if not database_url and hasattr(self.settings, "get"):
                database_url = self.settings.get("postgres", {}).get("database_url")
        
        if not database_url:
            raise ValueError("DATABASE_URL must be provided in environment or settings")
        
        # Similarly get echo setting
        try:
            echo = getattr(self.settings, "db_echo", False)
        except (AttributeError, TypeError):
            echo = False
            
        if not isinstance(echo, bool) and hasattr(self.settings, "get"):
            echo = self.settings.get("postgres", {}).get("echo", False)
        
        try:
            # Create pool with explicit min and max size to prevent connection exhaustion
            self.pool = await asyncpg.create_pool(
                database_url,
                min_size=self.min_size,
                max_size=self.max_size,
                command_timeout=60.0
            )
            
            if echo:
                logger.info(f"Connected to PostgreSQL at {database_url.split('@')[1]}")
            else:
                # Hide credentials in logs
                db_info = database_url.split("@")[1] if "@" in database_url else "database"
                logger.info(f"Connected to PostgreSQL at {db_info} (pool: min={self.min_size}, max={self.max_size})")
            
            # Check and create tables only if necessary
            await self._create_tables()
            
            return self.pool
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {str(e)}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from PostgreSQL."""
        if self.pool and not self.pool._closed:
            await self.pool.close()
            self.pool = None
            logger.info("Disconnected from PostgreSQL")
    
    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.disconnect()

    async def _create_tables(self) -> None:
        """Check if tables exist and create only if they don't."""
        async with self.pool.acquire() as conn:
            # Check if cache_data table exists
            table_exists = await conn.fetchval('''
                SELECT EXISTS (
                    SELECT FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename = 'cache_data'
                )
            ''')
            
            if not table_exists:
                logger.info("Creating cache_data table as it doesn't exist")
                # Create table for key-value storage
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS cache_data (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        expires_at TIMESTAMP WITH TIME ZONE
                    )
                ''')
                
                # Create index on expiration for cleanup
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS cache_data_expires_at_idx
                    ON cache_data (expires_at)
                ''')
            else:
                # Check if index exists
                index_exists = await conn.fetchval('''
                    SELECT EXISTS (
                        SELECT FROM pg_indexes
                        WHERE schemaname = 'public'
                        AND indexname = 'cache_data_expires_at_idx'
                    )
                ''')
                
                if not index_exists:
                    logger.info("Creating cache_data_expires_at_idx index as it doesn't exist")
                    await conn.execute('''
                        CREATE INDEX IF NOT EXISTS cache_data_expires_at_idx
                        ON cache_data (expires_at)
                    ''')


class PostgresCache:
    """PostgreSQL cache implementation."""
    
    def __init__(self, connection_manager: PostgresConnection = None):
        """Initialize PostgreSQL cache.
        
        Args:
            connection_manager: PostgreSQL connection manager (optional)
        """
        self.connection_manager = connection_manager or PostgresConnection(min_size=2, max_size=10)
    
    async def connect(self) -> None:
        """Connect to the database."""
        await self.connection_manager.connect()
    
    async def disconnect(self) -> None:
        """Disconnect from the database."""
        await self.connection_manager.disconnect()
    
    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.disconnect()
        
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Value or None if key doesn't exist or has expired
        """
        pool = await self.connection_manager.connect()
        async with pool.acquire() as conn:
            # First, delete expired entries
            await conn.execute('''
                DELETE FROM cache_data
                WHERE expires_at < NOW()
            ''')
            
            # Then get the value if it exists
            row = await conn.fetchrow('''
                SELECT value FROM cache_data
                WHERE key = $1 AND (expires_at IS NULL OR expires_at > NOW())
            ''', key)
            
            return row['value'] if row else None
    
    async def set(self, key: str, value: Any) -> None:
        """Set value in cache with no expiration.
        
        Args:
            key: Cache key
            value: Value to set
        """
        await self.setex(key, None, value)
    
    async def setex(self, key: str, seconds: Optional[int], value: Any) -> None:
        """Set value in cache with expiration.
        
        Args:
            key: Cache key
            seconds: Expiration time in seconds, or None for no expiration
            value: Value to set
        """
        pool = await self.connection_manager.connect()
        
        # Calculate expiration time
        expires_at = None
        if seconds is not None:
            expires_at = datetime.utcnow() + timedelta(seconds=seconds)
        
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO cache_data (key, value, expires_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (key) DO UPDATE
                SET value = $2, expires_at = $3
            ''', key, str(value), expires_at)
    
    async def delete(self, key: str) -> None:
        """Delete key from cache.
        
        Args:
            key: Cache key
        """
        pool = await self.connection_manager.connect()
        async with pool.acquire() as conn:
            await conn.execute('''
                DELETE FROM cache_data
                WHERE key = $1
            ''', key)
    
    async def keys(self, pattern: str) -> List[str]:
        """Get keys matching pattern.
        
        Args:
            pattern: SQL LIKE pattern to match
            
        Returns:
            List of matching keys
        """
        # Convert Redis pattern to SQL LIKE pattern
        sql_pattern = pattern.replace('*', '%')
        
        pool = await self.connection_manager.connect()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT key FROM cache_data
                WHERE key LIKE $1 AND (expires_at IS NULL OR expires_at > NOW())
            ''', sql_pattern)
            
            return [row['key'] for row in rows]
    
    async def expire(self, key: str, seconds: int) -> None:
        """
        Set expiration time on key.
        
        Args:
            key: Cache key
            seconds: Expiration time
        """
        pool = await self.connection_manager.connect()
        expires_at = datetime.utcnow() + timedelta(seconds=seconds)
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE cache_data
                SET expires_at = $2
                WHERE key = $1
            ''', key, expires_at)


# Global PostgreSQL cache instance
postgres_client = PostgresCache()