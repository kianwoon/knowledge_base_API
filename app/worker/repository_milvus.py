#!/usr/bin/env python3
"""Repository implementations for the Worker module using Milvus."""


import time
from typing import Dict, Any, Optional, List
from loguru import logger
 
from app.core.const import JobType
from app.core.milvus import milvus_client
from app.worker.interfaces import JobRepository
from app.models.email import EmailAnalysis
from app.models.job import Job


class MilvusRepository(JobRepository):
    """Milvus implementation of the JobRepository interface."""
    
    _collection_cache = {}  # Simple cache for collection existence
    _cache_expire_time = {}

    def __init__(self, source_collection_name="_sharepoint_knowledge", target_collection_name="_knowledge_base_bm", vector_size=1024):
        """
        Initialize MilvusRepository.
        
        Args:
            source_collection_name: Default Milvus source collection name (default: __sharepoint_knowledge)
            target_collection_name: Default Milvus target collection name (default: _knowledge_base_bm)
            vector_size: Size of the vector embeddings (default: 1536 for OpenAI embeddings)
        """

        self.target_collection_name = target_collection_name
        self.vector_size = vector_size
        self._collections_cache = None
        self._collections_cache_time = 0
        self._collections_cache_ttl = 300

    def get_job_id(self, job_key: str) -> str:
        """Retrieve job ID based on the job key."""
        return job_key.split(":")[-1]

    async def ping(self) -> None:
        """Ping the Milvus server to check connectivity."""
        try:
            await milvus_client.ping()
        except Exception as e:
            logger.error(f"Error pinging Milvus: {str(e)}")
            raise

    async def connect_with_retry(self) -> None:
        """Connect to Milvus with retry logic."""
        try:
            await milvus_client.connect_with_retry()
        except Exception as e:
            logger.error(f"Error connecting to Milvus: {str(e)}")
            raise

    async def connect(self) -> None:
        """Connect to Milvus server."""
        try:
            await milvus_client.connect()
        except Exception as e:
            logger.error(f"Error connecting to Milvus: {str(e)}")
            raise
            
    async def close(self) -> None:
        """Close connection to Milvus server."""
        # Milvus client is a singleton with shared connections,
        # so we don't actually close connections here to avoid 
        # affecting other users of the client.
        logger.debug("MilvusRepository close() called (no-op)")
        pass

    async def __aenter__(self):
        """Context manager entry point."""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point."""
        await self.close()

    async def get_collections(self) -> List[str]:
        """
        Get all collections from Milvus with caching to reduce server calls.
        
        Returns:
            List of collection names
        """
        try:
            current_time = time.time()
            
            # Return cached collections if not expired
            if self._collections_cache is not None and (current_time - self._collections_cache_time < self._collections_cache_ttl):
                logger.debug("Using cached collections")
                return self._collections_cache
                
            # Get collections from server
            collections = await milvus_client.get_collections()
            
            # Cache the results
            self._collections_cache = collections
            self._collections_cache_time = current_time
            
            logger.debug(f"Updated collections cache with {len(collections)} collections")
            return collections
        except Exception as e:
            # If we have a cache, return it even if expired rather than failing
            if self._collections_cache is not None:
                logger.warning(f"Error getting collections, using expired cache: {str(e)}")
                return self._collections_cache
            
            logger.error(f"Error getting collections: {str(e)}")
            return []
    
    async def _ensure_collection_exists(self, collection_name: str = None) -> None:
        """Ensure that the collection exists in Milvus.
        
        Args:
            collection_name: Optional collection name. If not provided, uses the default.
        """
        try:
            # Ensure collection exists
            await milvus_client.ensure_collection_exists(
                collection_name=collection_name,
                vector_size=self.vector_size
            )
        except Exception as e:
            logger.error(f"Error ensuring Milvus collection exists: {str(e)}")
            raise
    
    async def get_job_data(self, job_id: str, owner: str = None) -> Optional[str]:
        """
        Get job data from Milvus.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job data as JSON string or None if not found
        """
        pass
    
    async def get_job_type(self, job_id: str, owner: str = None) -> Optional[str]:
        """
        Get job type from Milvus.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job type or None if not found
        """
        try:
            return JobType.EMBEDDING.value
        except Exception as e:
            logger.error(f"Error getting job type for job {job_id} from Milvus: {str(e)}")
            return None
    
    async def store_job_results(self, job_id: str, results: Dict[str, Any], owner: str = None, expiration: int=None) -> None:
        """
        Store job results in Milvus.
        
        Args:
            job_id: Job ID
            results: Job results 
        """
        try:
            # Extract owner from results if available
            owner = owner.replace("@", "_").replace(".", "_") 
            collection_name = owner + self.target_collection_name
            
            for result in results:
                embeddings = result.get("embeddings", [])
                extra_data = result.get("extra_data", {}) 
                
                # Save embeddings using the MilvusClientManager
                result = await milvus_client.save_embeddings(
                        job_id=job_id,
                        embeddings=embeddings,
                        collection_name=collection_name,
                        extra_data=extra_data
                    )
            logger.info(f"Stored job results for job {job_id} in Milvus collection {collection_name}")
        except Exception as e:
            logger.error(f"Error storing job results for job {job_id} in Milvus: {str(e)}")
            raise
    
    async def update_job_status(self, job_id: str, status: str, owner: str, expiration: int = 60 * 60) -> None:
        """
        Update job status in Milvus.
        
        Args:
            job_id: Job ID
            status: Job status
            expiration: Expiration time in seconds (default: 1 hour) - not used in Milvus
        """
        pass
    
    async def store_job_error(self, job_id: str, error: str, expiration: int = 60 * 60 * 24) -> None:
        """
        Store job error in Milvus.
        
        Args:
            job_id: Job ID
            error: Error message
            expiration: Expiration time in seconds (default: 24 hours) - not used in Milvus
        """
        pass

    async def get_pending_jobs(self, job_type: str, filter: Optional[str], payload: List[str]) -> List[str]:
        """
        Get pending jobs from Milvus across all user collections.
        
        Returns:
            List of pending Job objects
        """
        pass
 
    async def get_job_status(self, job: Job) -> Optional[str]:
        """
        Get job status from Milvus.
        
        Args:
            job: Job object
            
        Returns:
            Job status or None if not found
        """
        pass

    async def store_query_criteria(self, job_id: str, owner: str, query_criteria: Dict[str, Any]) -> str:
        """
        Store query criteria in Milvus.
        
        Args: 
            job_id: Job ID
            owner: Owner email address
            query_criteria: Query criteria
            
        Returns:
            Point ID of the stored query criteria
        """
        pass
    
    async def store_analysis_results(self, job_id: str, analysis: EmailAnalysis, owner: str) -> str:
        """
        Store analysis results in Milvus.
        
        Args: 
            job_id: Job ID
            analysis: Email analysis
            owner: Owner email address
            
        Returns:
            Point ID of the stored analysis results
        """
        pass 
    
    async def get_emails_by_job_id(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Get emails by job ID from Milvus.
        
        Args:
            job_id: Job ID
            
        Returns:
            List of email entries
        """
        pass
    
    async def get_analysis_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get analysis chart by job ID from Milvus.
        
        Args:
            job_id: Job ID
            
        Returns:
            Analysis chart entry or None if not found
        """
        pass

    async def claim_job(self, job_id: str, owner: str, ttl_seconds: int = 60 * 5) -> bool:
        """
        Atomically claim a job for processing. For Milvus implementation,
        we'll use a field to track the lock status.
        
        Args:
            job_id: The ID of the job to claim
            owner: The owner of the job
            ttl_seconds: Time-to-live for the claim in seconds (default: 5 minutes)
            
        Returns:
            bool: True if the job was successfully claimed, False otherwise
        """
        pass