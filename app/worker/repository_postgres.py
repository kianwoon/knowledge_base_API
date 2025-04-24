#!/usr/bin/env python3
"""PostgreSQL repository implementation for the Worker module."""

from datetime import datetime, timedelta, timezone
import json
import time
from typing import Dict, Any, Optional, List
from loguru import logger


from app.worker.interfaces import JobRepository
from app.core.postgres_cache import PostgresConnection


class PostgresRepository(JobRepository):
    """PostgreSQL implementation of the JobRepository interface."""
    
    def __init__(self, table_name="processed_files", max_pool_size=10):
        """
        Initialize PostgresRepository.
        
        Args:
            table_name: PostgreSQL table name (default: processed_files)
            max_pool_size: Maximum connections in the pool (default: 10)
        """
        self.table_name = table_name
        self.connection_manager = PostgresConnection()
        self.pool = None
        self.max_pool_size = max_pool_size
        # Required columns for file data
        self.file_columns = [
            "id", "owner_email", "source_type", "original_filename", 
            "content_type", "size_bytes", "r2_object_key", "status", "additional_data"
        ]
    
    async def connect_with_retry(self) -> None:
        """Connect to PostgreSQL with retry logic."""
        MAX_RETRIES = 5
        retry_count = 0
        
        # If pool already exists and is not closed, return
        if self.pool and not self.pool._closed:
            return
            
        while retry_count < MAX_RETRIES:
            try:
                # Set min_size and max_size for the connection pool to prevent exhausting connections
                self.pool = await self.connection_manager.connect()
                await self._ensure_table_exists()
                logger.info(f"Connected to PostgreSQL repository (table: {self.table_name})")
                return
            except Exception as e:
                retry_count += 1
                wait_time = 2 ** retry_count  # Exponential backoff
                logger.error(f"Failed to connect to PostgreSQL (attempt {retry_count}/{MAX_RETRIES}): {str(e)}")
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
        
        raise Exception(f"Failed to connect to PostgreSQL after {MAX_RETRIES} attempts")

    async def close(self) -> None:
        """Close the PostgreSQL connection pool."""
        if self.pool and not self.pool._closed:
            await self.connection_manager.disconnect()
            self.pool = None
            logger.info("Closed PostgreSQL repository connection pool")

    async def __aenter__(self):
        """Enter async context manager."""
        await self.connect_with_retry()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        await self.close()

    async def ping(self) -> None:
        """Ping the PostgreSQL server to check connectivity."""
        try:
            if not self.pool:
                self.pool = await self.connection_manager.connect()
            
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")
            logger.debug("PostgreSQL repository ping successful")
        except Exception as e:
            logger.error(f"Error pinging PostgreSQL: {str(e)}")
            raise
    
    async def _ensure_table_exists(self) -> None:
        """Ensure that the table exists in PostgreSQL."""

        pass # Placeholder for table creation logic if needed
 

    def get_job_id(self, job_key: str) -> str:
        """Retrieve job ID based on the job key."""
        parts = job_key.split(":")
        if len(parts) >= 2:
            return parts[1]
        return job_key

    async def get_job_data(self, job_id: int, owner: str = None) -> Optional[str]:
        """
        Get job data from PostgreSQL with all required columns.
        
        Args:
            job_id: Job ID
            owner: Owner of the job (optional)
            
        Returns:
            Job data as JSON string or None if not found
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
                
            async with self.pool.acquire() as conn:
                # Select all required columns instead of just 'data'
                columns_str = ", ".join(self.file_columns)
                query = f"SELECT {columns_str} FROM {self.table_name} WHERE id = $1"
                params = [job_id]
                
                # if owner:
                #     query += " AND owner_email = $2"
                #     params.append(owner)
                
                row = await conn.fetchrow(query, *params)
                
                if not row:
                    return None
                
                # Convert record to dictionary
                result = dict(row)
                
                # Ensure all fields are JSON serializable
                for key, value in result.items():
                    if isinstance(value, datetime):
                        result[key] = value.isoformat()
                
                # Return as JSON string
                return json.dumps(result)
        except Exception as e:
            logger.error(f"Error getting file data for ID {job_id} from PostgreSQL: {str(e)}")
            return None
    
    async def get_job_type(self, job_id: str, owner: str = None) -> Optional[str]:
        """
        Get job type and other file information from PostgreSQL.
        
        Args:
            job_id: Job ID
            owner: Owner of the job (optional)
            
        Returns:
            Job type and other information as JSON string or None if not found
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
                
            async with self.pool.acquire() as conn:
                # Select all required columns
                columns_str = ", ".join(self.file_columns)
                query = f"SELECT {columns_str} FROM {self.table_name} WHERE id = $1"
                params = [job_id]
                
                if owner:
                    query += " AND owner_email = $2"
                    params.append(owner)
                
                row = await conn.fetchrow(query, *params)
                
                if not row:
                    return None
                
                # Convert record to dictionary
                result = dict(row)
                
                # Handle datetime objects for JSON serialization
                for key, value in result.items():
                    if isinstance(value, datetime):
                        result[key] = value.isoformat()
                
                # Return as JSON string
                return json.dumps(result)
        except Exception as e:
            logger.error(f"Error getting file information for ID {job_id} from PostgreSQL: {str(e)}")
            return None
    
    async def store_job_results(self, job_id: str, results: Dict[str, Any], owner: str = None, expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Store job results in PostgreSQL.
        
        Args:
            job_id: Job ID
            results: Job results
            owner: Owner of the job (optional)
            expiration: Expiration time in seconds (default: 7 days)
        """
        pass # Placeholder for storing job results logic
    
    async def update_job_status(self, job_id: str, status: str, owner: str = None, expiration: int = None) -> None:
        """
        Update job status in PostgreSQL.
        
        Args:
            job_id: Job ID
            status: Job status
            owner: Owner of the job (optional)
            expiration: Expiration time in seconds (default: 7 days)
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
                
            async with self.pool.acquire() as conn:
                query = f'''
                    UPDATE {self.table_name}
                    SET status = $1, 
                        updated_at = NOW()
                '''
                
                params = [status]
                
                    
                query += f" WHERE id = ${len(params) + 1}"
                # Convert job_id to integer to match PostgreSQL column type
                params.append(int(job_id))
                
                await conn.execute(query, *params)
                logger.info(f"Updated job status for job {job_id} to {status} in PostgreSQL")
        except Exception as e:
            logger.error(f"Error updating job status for job {job_id} in PostgreSQL: {str(e)}")
            raise
    
    async def store_job_error(self, job_id: str, error: str, expiration: int = None) -> None:
        """
        Store job error in PostgreSQL.
        
        Args:
            job_id: Job ID
            error: Error message
            expiration: Expiration time in seconds (default: 24 hours)
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
                
 
                
            async with self.pool.acquire() as conn:
                await conn.execute(f'''
                    UPDATE {self.table_name}
                    SET error_message = $1, 
                        status = 'failed',
                        updated_at = NOW() 
                    WHERE id = $2
                ''', error, int(job_id))
                
                logger.info(f"Stored job error for job {job_id} in PostgreSQL")
        except Exception as e:
            logger.error(f"Error storing job error for job {job_id} in PostgreSQL: {str(e)}")
            raise
 
    async def get_pending_jobs(self, job_type:str) -> str:
        """
        Get pending jobs from PostgreSQL with all required columns.
        
        Returns:
            JSON string containing a list of pending jobs data
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
                
            pending_jobs = []
            
            async with self.pool.acquire() as conn:

                query = f'''
                    SELECT id,owner_email,source_type ,status
                    FROM {self.table_name}
                    WHERE status = 'pending_analysis'
                    ORDER BY created_at ASC
                    LIMIT 4
                '''
                
                # Execute query
                rows = await conn.fetch(query)
                
                # Format as list of dictionaries
                for row in rows:
                    job_dict = dict(row)
                    
                    # Handle datetime objects for JSON serialization
                    for key, value in job_dict.items():
                        if isinstance(value, datetime):
                            job_dict[key] = value.isoformat()
                            
                    pending_jobs.append(f"{job_dict['source_type']}:{job_dict['id']}:{job_dict['owner_email']}")
                    await self.update_job_status(job_dict["id"],"scheduled", None)

                # Return as JSON string
                return pending_jobs
        except Exception as e:
            logger.error(f"Error getting pending jobs from PostgreSQL: {str(e)}")
            return json.dumps([])  # Return empty array as JSON if there's an error
 
    async def get_job_status(self, job_key: str, owner: str = None) -> Optional[str]:
        """
        Get job status and other file information from PostgreSQL.
        
        Args:
            job_key: Job key or job ID
            owner: Owner of the job (optional)
            
        Returns:
            Job status and file information as JSON string or None if not found
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
            
            # Extract job ID from job key if needed
            job_id = self.get_job_id(job_key) if ":" in job_key else job_key
                
            async with self.pool.acquire() as conn:
                # Select all required columns
                columns_str = ", ".join(self.file_columns)
                query = f"SELECT {columns_str} FROM {self.table_name} WHERE id = $1"
                params = [job_id]
                
                if owner:
                    query += " AND owner_email = $2"
                    params.append(owner)
                
                row = await conn.fetchrow(query, *params)
                
                if not row:
                    return None
                
                # Convert record to dictionary
                result = dict(row)
                
                # Handle datetime objects for JSON serialization
                for key, value in result.items():
                    if isinstance(value, datetime):
                        result[key] = value.isoformat()
                
                # Return as JSON string
                return json.dumps(result)
        except Exception as e:
            logger.error(f"Error getting file information for ID {job_key} from PostgreSQL: {str(e)}")
            return None

    async def create_job(self, job_id: str, job_type: str, job_data: Dict[str, Any], owner: str = None, expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Create a new job in PostgreSQL.
        
        Args:
            job_id: Job ID
            job_type: Job type
            job_data: Job data
            owner: Owner of the job (optional)
            expiration: Expiration time in seconds (default: 7 days)
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
                
            # Calculate expiration time
            expires_at = None
            if expiration:
                tz_utc = timezone.utc
                expires_at = datetime.now(tz_utc) + timedelta(seconds=expiration)
                
            async with self.pool.acquire() as conn:
                await conn.execute(f'''
                    INSERT INTO {self.table_name} (
                        id, job_type, owner_email, status, data, created_at, updated_at, expires_at
                    ) VALUES ($1, $2, $3, $4, $5, NOW(), NOW(), $6)
                    ON CONFLICT (id) DO UPDATE
                    SET job_type = $2,
                        owner_email = $3,
                        status = $4,
                        data = $5,
                        updated_at = NOW(),
                        expires_at = $6
                ''', job_id, job_type, owner, 'pending', job_data, expires_at)
                
                logger.info(f"Created job {job_id} in PostgreSQL")
        except Exception as e:
            logger.error(f"Error creating job {job_id} in PostgreSQL: {str(e)}")
            raise

    async def claim_job(self, job_id: str, owner: str = None, ttl_seconds: int = 60 * 5) -> bool:
        """
        Atomically claim a job for processing.
        
        Args:
            job_id: The ID of the job to claim
            owner: The owner of the job (optional)
            ttl_seconds: Time-to-live for the claim in seconds (default: 5 minutes)
            
        Returns:
            bool: True if the job was successfully claimed, False otherwise
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
                
            async with self.pool.acquire() as conn:
                # Use a transaction for atomicity
                async with conn.transaction():
                    # Check current status and try to claim
                    query = f"SELECT status FROM {self.table_name} WHERE id = $1"
                    params = [job_id]
                    
                    if owner:
                        query += " AND owner_email = $2"
                        params.append(owner)
                    
                    query += " FOR UPDATE"  # Lock the row for update
                    
                    status = await conn.fetchval(query, *params)
                    
                    # Only claim if job is in 'pending' status
                    if status != 'pending':
                        return False
                    
                    # Calculate lock expiration
                    lock_expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                    
                    # Update status to 'processing' and set lock expiration
                    update_query = f'''
                        UPDATE {self.table_name} 
                        SET status = 'processing',
                            updated_at = NOW(),
                            expires_at = $1
                        WHERE id = $2
                    '''
                    update_params = [lock_expires_at, job_id]
                    
                    if owner:
                        update_query += " AND owner_email = $3"
                        update_params.append(owner)
                    
                    await conn.execute(update_query, *update_params)
                    
                    return True
                    
        except Exception as e:
            logger.error(f"Error claiming job {job_id}: {str(e)}")
            return False

    async def get_job(self, job_id: str, owner: str = None) -> Optional[Dict[str, Any]]:
        """
        Get complete job record with all columns from PostgreSQL.
        
        Args:
            job_id: Job ID
            owner: Owner of the job (optional)
            
        Returns:
            Dictionary with all job fields or None if not found
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
                
            async with self.pool.acquire() as conn:
                query = f"SELECT * FROM {self.table_name} WHERE id = $1"
                params = [job_id]
                
                if owner:
                    query += " AND owner_email = $2"
                    params.append(owner)
                
                row = await conn.fetchrow(query, *params)
                
                if not row:
                    return None
                
                # Convert record to dictionary
                job_dict = dict(row)
                
                # Ensure JSONB fields are properly converted to Python dictionaries
                if job_dict.get('data') is not None:
                    job_dict['data'] = job_dict['data']
                if job_dict.get('results') is not None:
                    job_dict['results'] = job_dict['results']
                
                return job_dict
        except Exception as e:
            logger.error(f"Error getting job record for job {job_id} from PostgreSQL: {str(e)}")
            return None
    
    async def get_job_columns(self, job_id: str, columns: List[str], owner: str = None) -> Optional[Dict[str, Any]]:
        """
        Get specific columns from a job record.
        
        Args:
            job_id: Job ID
            columns: List of column names to retrieve
            owner: Owner of the job (optional)
            
        Returns:
            Dictionary with requested job fields or None if not found
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
                
            # Ensure we have valid column names to prevent SQL injection
            valid_columns = {'id', 'job_type', 'owner_email', 'status', 'data', 'results', 
                            'error', 'created_at', 'updated_at', 'expires_at'}
            
            # Filter out invalid column names
            safe_columns = [col for col in columns if col in valid_columns]
            
            if not safe_columns:
                logger.error(f"No valid columns specified for job {job_id}")
                return None
                
            # Create a comma-separated list of column names
            columns_str = ', '.join(safe_columns)
                
            async with self.pool.acquire() as conn:
                query = f"SELECT {columns_str} FROM {self.table_name} WHERE id = $1"
                params = [job_id]
                
                if owner:
                    query += " AND owner_email = $2"
                    params.append(owner)
                
                row = await conn.fetchrow(query, *params)
                
                if not row:
                    return None
                
                # Convert record to dictionary
                result = dict(row)
                
                # Ensure JSONB fields are properly handled
                if 'data' in result and result['data'] is not None:
                    result['data'] = result['data']
                if 'results' in result and result['results'] is not None:
                    result['results'] = result['results']
                
                return result
        except Exception as e:
            logger.error(f"Error getting columns {columns} for job {job_id} from PostgreSQL: {str(e)}")
            return None
    
    async def find_jobs(self, filters: Dict[str, Any], limit: int = 10, 
                        offset: int = 0, order_by: str = "created_at DESC") -> List[Dict[str, Any]]:
        """
        Find jobs matching specific filters with pagination.
        
        Args:
            filters: Dictionary of filter conditions (column: value)
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip (for pagination)
            order_by: SQL ORDER BY clause
            
        Returns:
            List of dictionaries containing job data
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
            
            # Valid columns that can be filtered
            valid_columns = {'id', 'job_type', 'owner_email', 'status', 'created_at', 'updated_at'}
            
            # Build WHERE clause
            where_clauses = []
            params = []
            param_index = 1
            
            for col, value in filters.items():
                if col in valid_columns:
                    where_clauses.append(f"{col} = ${param_index}")
                    params.append(value)
                    param_index += 1
            
            # Build query
            query = f"SELECT * FROM {self.table_name}"
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            # Validate order_by to prevent SQL injection
            safe_columns = {'id', 'job_type', 'owner_email', 'status', 'created_at', 'updated_at'}
            order_parts = order_by.split()
            if (len(order_parts) >= 1 and 
                order_parts[0].lower() in map(str.lower, safe_columns) and
                (len(order_parts) == 1 or 
                 (len(order_parts) == 2 and order_parts[1].upper() in ('ASC', 'DESC')))):
                query += f" ORDER BY {order_by}"
            else:
                # Default to a safe ordering if invalid
                query += " ORDER BY created_at DESC"
            
            query += f" LIMIT ${param_index} OFFSET ${param_index + 1}"
            params.extend([limit, offset])
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                
                result = []
                for row in rows:
                    job_dict = dict(row)
                    
                    # Ensure JSONB fields are properly handled
                    if job_dict.get('data') is not None:
                        job_dict['data'] = job_dict['data']
                    if job_dict.get('results') is not None:
                        job_dict['results'] = job_dict['results']
                    
                    result.append(job_dict)
                
                return result
        except Exception as e:
            logger.error(f"Error finding jobs with filters {filters} in PostgreSQL: {str(e)}")
            return []
    
    async def get_job_count(self, filters: Dict[str, Any] = None) -> int:
        """
        Get count of jobs matching specific filters.
        
        Args:
            filters: Dictionary of filter conditions (column: value)
            
        Returns:
            Number of matching jobs
        """
        try:
            if not self.pool:
                await self.connect_with_retry()
            
            # Valid columns that can be filtered
            valid_columns = {'id', 'job_type', 'owner_email', 'status', 'created_at', 'updated_at'}
            
            # Build WHERE clause
            where_clauses = []
            params = []
            param_index = 1
            
            if filters:
                for col, value in filters.items():
                    if col in valid_columns:
                        where_clauses.append(f"{col} = ${param_index}")
                        params.append(value)
                        param_index += 1
            
            # Build query
            query = f"SELECT COUNT(*) FROM {self.table_name}"
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            async with self.pool.acquire() as conn:
                count = await conn.fetchval(query, *params)
                return count or 0
        except Exception as e:
            logger.error(f"Error counting jobs with filters {filters} in PostgreSQL: {str(e)}")
            return 0