#!/usr/bin/env python3
"""Repository implementations for the Worker module using Milvus."""

from datetime import datetime, timedelta, timezone
import json
import time
from typing import Dict, Any, Optional, List
from loguru import logger
 
from app.core.const import JobType
from app.core.milvus import milvus_client
from app.worker.interfaces import JobRepository
from app.models.qdrant_mail import QdrantQueryCriteria, QdrantQueryCriteriaEntry, QdrantAnalysisChartEntry
from app.models.email import EmailAnalysis
from app.models.job import Job


class MilvusRepository(JobRepository):
    """Milvus implementation of the JobRepository interface."""
    
    _collection_cache = {}  # Simple cache for collection existence
    _cache_expire_time = {}

    def __init__(self, source_collection_name="_sharepoint_knowledge", target_collection_name="_knowledge_base_bm", vector_size=1536):
        """
        Initialize MilvusRepository.
        
        Args:
            source_collection_name: Default Milvus source collection name (default: __sharepoint_knowledge)
            target_collection_name: Default Milvus target collection name (default: _knowledge_base_bm)
            vector_size: Size of the vector embeddings (default: 1536 for OpenAI embeddings)
        """
        self.source_collection_name = source_collection_name
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
        try:
            # We need to search the specific collection for this job_id
            collection_name = owner + self.source_collection_name
            
            # Query for query_criteria entry with the given job_id
            results = await milvus_client.retrieve(
                collection_name=collection_name,
                ids=[job_id],
                with_vectors=False,
            )
            
            if results:
                # Extract data from the payload
                job_data = results[0]["payload"]
                    
                # Convert to JSON string
                return json.dumps(job_data)
            else:
                return {}
        except Exception as e:
            logger.error(f"Error getting job data for job {job_id} from Milvus: {str(e)}")
            return {}
    
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
        try:
            # We need to search the specific collection for this job_id
            collection_name = owner + self.source_collection_name
            
            try:
                # Check if job_id exists in this collection
                results = await milvus_client.retrieve(
                    collection_name=collection_name,
                    ids=[job_id],
                    with_vectors=False,
                )

                if results:
                    # Create a timezone object for UTC+8
                    tz_utc8 = timezone(timedelta(hours=8))
                    # Get current time with UTC+8 timezone
                    now_utc8 = datetime.now(tz_utc8)
                    
                    # Update the status field
                    await milvus_client.set_payload(
                        collection_name=collection_name,
                        payload={"analysis_status": status, "lastAnalysisUpdate": now_utc8.isoformat()},
                        points=[job_id]
                    )
                    logger.info(f"Updated job status for job {job_id} in collection {collection_name} to {status}")
                    return
            except Exception as e:
                # Skip if collection doesn't exist or other issues
                logger.error(f"Collection not found: {str(e)}")
                return
            
            logger.warning(f"Could not find job {job_id} in any collection to update status")
            return
        except Exception as e:
            logger.error(f"Error updating job status for job {job_id} in Milvus: {str(e)}")
            raise
    
    async def store_job_error(self, job_id: str, error: str, expiration: int = 60 * 60 * 24) -> None:
        """
        Store job error in Milvus.
        
        Args:
            job_id: Job ID
            error: Error message
            expiration: Expiration time in seconds (default: 24 hours) - not used in Milvus
        """
        try:
            # Get all collections that match the pattern
            collections = await milvus_client.get_collections()
            collection_names = [name for name in collections if name.endswith(self.source_collection_name)]
            
            for collection_name in collection_names:
                try:
                    # Find entities with the given job_id in this collection
                    filter_expr = f'job_id == "{job_id}"'
                    results, _ = await milvus_client.scroll(
                        collection_name=collection_name,
                        scroll_filter=filter_expr,
                        with_payload=["id", "job_id"],
                        limit=100  # Assuming there won't be more than 100 entries for a job
                    )
                    
                    # Update error for all entries
                    if results:
                        point_ids = [result["id"] for result in results]
                        
                        # Update the error field
                        await milvus_client.set_payload(
                            collection_name=collection_name,
                            payload={
                                "error": error,
                                "status": "failed"
                            },
                            points=point_ids
                        )
                        
                        logger.info(f"Stored job error for job {job_id} in collection {collection_name}")
                        return
                except Exception as e:
                    # Skip if collection doesn't exist or other issues
                    logger.warning(f"Skip if collection doesn't exist or other issues job {job_id} in Milvus: {str(e)}")
                    continue
            
            logger.warning(f"Could not find job {job_id} in any collection to store error")
        except Exception as e:
            logger.error(f"Error storing job error for job {job_id} in Milvus: {str(e)}")
            raise

    async def get_pending_jobs(self, job_type: str, filter: Optional[str], payload: List[str]) -> List[str]:
        """
        Get pending jobs from Milvus across all user collections.
        
        Returns:
            List of pending Job objects
        """
        try:
            # Get all collections that match the pattern
            collections = await milvus_client.get_collections()
            source_collections = [name for name in collections if name.endswith(self.source_collection_name)]
            
            pending_jobs = []
            tz_utc8 = timezone(timedelta(hours=8))
            
            # Track job IDs per collection
            collection_job_ids = {}
            
            # Search each collection for pending jobs
            for collection_name in source_collections:
                try:
                    owner = collection_name.replace(self.source_collection_name, "")
                    
                    # Query for entries with analysis_status="pending"
                    filter_expr = 'analysis_status == "pending"'
                    results, _ = await milvus_client.scroll(
                        collection_name=collection_name,
                        scroll_filter=filter_expr,
                        with_payload=payload,
                        limit=10  # Limit to 10 pending jobs per collection
                    )
                    
                    # Initialize collection job IDs set if not exists
                    if collection_name not in collection_job_ids:
                        collection_job_ids[collection_name] = set()
                    
                    # Extract job IDs and format as Job objects
                    for point in results:
                        job_id = point["id"]
                        if job_id:
                            collection_job_ids[collection_name].add(job_id)
                            pending_jobs.append(f"{job_type}:{job_id}:{owner}")
                    
                except Exception as e:
                    logger.error(f"Error querying collection {collection_name}: {str(e)}")
                    continue

            # Update job statuses for each collection
            now_utc8 = datetime.now(tz_utc8)
            for collection_name, job_ids in collection_job_ids.items():
                if job_ids:
                    # Update the status field for this collection
                    await milvus_client.set_payload(
                        collection_name=collection_name,
                        payload={"analysis_status": "scheduled", "lastAnalysisUpdate": now_utc8.isoformat()},
                        points=list(job_ids)
                    )
                    logger.info(f"Updated job status to 'scheduled' in collection {collection_name} for {len(job_ids)} jobs")

            return pending_jobs
        except Exception as e:
            logger.error(f"Error getting pending jobs from Milvus: {str(e)}")
            return []
 
    async def get_job_status(self, job: Job) -> Optional[str]:
        """
        Get job status from Milvus.
        
        Args:
            job: Job object
            
        Returns:
            Job status or None if not found
        """
        try: 
            collection_name = job.owner + self.source_collection_name
            
            # Query for any entry with the given job_id
            results = await milvus_client.retrieve(
                collection_name=collection_name,
                ids=[job.id],
                with_vectors=False,
            )
            
            if results:
                # Return the status of the entry
                return results[0]["payload"].get("analysis_status")
            return None
        except Exception as e:
            logger.error(f"Error getting job status for job {job.id} from Milvus: {str(e)}")
            return None

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
        try:
            # Get the collection name for this owner
            collection_name = owner + self.source_collection_name
            
            # Ensure collection exists
            await self._ensure_collection_exists(collection_name)
            
            # Create query criteria entry using the Qdrant model
            criteria = QdrantQueryCriteria(
                folder=query_criteria.get("folder"),
                from_date=query_criteria.get("from_date"),
                to_date=query_criteria.get("to_date"),
                keywords=query_criteria.get("keywords", [])
            )
            
            query_entry = QdrantQueryCriteriaEntry(
                job_id=job_id,
                owner=owner,
                query_criteria=criteria
            )
            
            # Create a dummy vector for now (in production, this would be an actual embedding)
            dummy_vector = [0.0] * self.vector_size
            
            # Generate a unique point ID
            point_id = f"{job_id}-query"
            
            # Prepare the entity for insertion
            entity = {
                "id": point_id,
                "vector": dummy_vector,
                "job_id": job_id,
                "analysis_status": "pending",
                "type": "query_criteria",
                "content": json.dumps(query_entry.model_dump()),
                "chunk_index": 0
            }
            
 
            
            logger.info(f"Stored query criteria for job {job_id} in Milvus")
            return point_id
        except Exception as e:
            logger.error(f"Error storing query criteria for job {job_id} in Milvus: {str(e)}")
            raise
    
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
        try:
            # Get the collection name for this owner
            collection_name = owner + self.source_collection_name
            
            # Ensure collection exists
            await self._ensure_collection_exists(collection_name)
            
            # Create analysis chart entry using the Qdrant model
            analysis_chart = QdrantAnalysisChartEntry.from_email_analysis(
                analysis=analysis,
                job_id=job_id,
                owner=owner
            )
            
 
            
            logger.info(f"Stored analysis results for job {job_id} in Milvus")
            return None
        except Exception as e:
            logger.error(f"Error storing analysis results for job {job_id} in Milvus: {str(e)}")
            raise
    
    async def get_emails_by_job_id(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Get emails by job ID from Milvus.
        
        Args:
            job_id: Job ID
            
        Returns:
            List of email entries
        """
        try:
            # Get all collections that match the pattern
            collections = await milvus_client.get_collections()
            collection_names = [name for name in collections if name.endswith(self.source_collection_name)]
            
            emails = []
            
            for collection_name in collection_names:
                # Query for email entries with the given job_id
                try:
                    filter_expr = f'job_id == "{job_id}" && type == "email"'
                    results, _ = await milvus_client.scroll(
                        collection_name=collection_name,
                        scroll_filter=filter_expr,
                        with_payload=["job_id", "type", "content"],
                        limit=100  # Limit to 100 emails per job
                    )
                    
                    # Extract email entries
                    for result in results:
                        emails.append(result["payload"])
                except Exception:
                    # Skip if collection doesn't exist or other issues
                    continue
            
            return emails
        except Exception as e:
            logger.error(f"Error getting emails for job {job_id} from Milvus: {str(e)}")
            return []
    
    async def get_analysis_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get analysis chart by job ID from Milvus.
        
        Args:
            job_id: Job ID
            
        Returns:
            Analysis chart entry or None if not found
        """
        try:
            # Get all collections that match the pattern
            collections = await milvus_client.get_collections()
            collection_names = [name for name in collections if name.endswith(self.source_collection_name)]
            
            for collection_name in collection_names:
                # Query for analysis chart entry with the given job_id
                try:
                    filter_expr = f'job_id == "{job_id}" && type == "analysis_chart"'
                    results, _ = await milvus_client.scroll(
                        collection_name=collection_name,
                        scroll_filter=filter_expr,
                        with_payload=["job_id", "type", "content"],
                        limit=1
                    )
                    
                    if results:
                        # Return the analysis chart entry
                        return results[0]["payload"]
                except Exception:
                    # Skip if collection doesn't exist or other issues
                    continue
                
            return None
        except Exception as e:
            logger.error(f"Error getting analysis chart for job {job_id} from Milvus: {str(e)}")
            return None

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
        try:
            # Get the collection name for this owner
            collection_name = owner + self.source_collection_name
            
            # Check if job exists and its status
            results = await milvus_client.retrieve(
                collection_name=collection_name,
                ids=[job_id],
                with_vectors=False
            )
            
            if not results:
                logger.warning(f"Job {job_id} not found in collection {collection_name}")
                return False
                
            # Check the current status
            current_status = results[0]["payload"].get("analysis_status")
            
            # Only claim if the job is in 'pending' status
            if current_status != "pending":
                logger.warning(f"Job {job_id} is not in pending status (current: {current_status})")
                return False
                
            # Set a lock with expiration (in Milvus we just update the status)
            now = datetime.now().isoformat()
            lock_expiry = (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat()
            
            success = await milvus_client.set_payload(
                collection_name=collection_name,
                payload={
                    "analysis_status": "processing",
                    "lock_acquired_at": now,
                    "lock_expires_at": lock_expiry
                },
                points=[job_id]
            )
            
            return success
        except Exception as e:
            logger.error(f"Error claiming job {job_id} for {owner}: {str(e)}")
            return False