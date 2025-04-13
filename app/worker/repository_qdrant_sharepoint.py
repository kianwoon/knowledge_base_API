#!/usr/bin/env python3
"""Repository implementations for the Worker module."""

from datetime import datetime, timedelta, timezone
import json
import time
from typing import Dict, Any, Optional, List
from loguru import logger
 
from app.core.const import JobType
from app.core.qdrant import qdrant_client
from app.worker.interfaces import JobRepository
from app.models.qdrant_mail import QdrantEmailEntry, QdrantQueryCriteria, QdrantQueryCriteriaEntry, QdrantAnalysisChartEntry
from app.models.email import EmailSchema, EmailAnalysis
from app.models.job import Job



class QdrantSharepointRepository(JobRepository):
    """Qdrant implementation of the JobRepository interface."""
    
    _collection_cache = {}  # Simple cache for collection existence
    _cache_expire_time = {}

    def __init__(self, source_collection_name="_sharepoint_knowledge", target_collection_name="_knowledge_base", vector_size=1536):
        """
        Initialize QdrantMailSharepointRepository.
        
        Args:
            source_collection_name: Default Qdrant source collection name (default: __sharepoint_knowledge)
            target_collection_name: Default Qdrant target collection name (default: _knowledge_base)
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
        """Ping the Qdrant server to check connectivity."""
        try:
            await qdrant_client.ping()
        except Exception as e:
            logger.error(f"Error pinging Qdrant: {str(e)}")
            raise

    async def connect_with_retry(self) -> None:
        """Connect to Qdrant with retry logic."""
        try:
            await qdrant_client.connect_with_retry()
        except Exception as e:
            logger.error(f"Error connecting to Qdrant: {str(e)}")
            raise

    async def get_collections(self) -> List[str]:
        """
        Get all collections from Qdrant with caching to reduce server calls.
        
        Returns:
            List of collection names
        """
        try:
            current_time = time.time()
            
            # Return cached collections if not expired
            if self._collections_cache is not None and (current_time - self._collections_cache_time < self._collections_cache_ttl):
                logger.debug("Using cached collections")
                return self._collections_cache
                
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # Get collections from server
            collections = client.get_collections().collections
            collection_names = [collection.name for collection in collections]
            
            # Cache the results
            self._collections_cache = collection_names
            self._collections_cache_time = current_time
            
            logger.debug(f"Updated collections cache with {len(collection_names)} collections")
            return collection_names
        except Exception as e:
            # If we have a cache, return it even if expired rather than failing
            if self._collections_cache is not None:
                logger.warning(f"Error getting collections, using expired cache: {str(e)}")
                return self._collections_cache
            
            logger.error(f"Error getting collections: {str(e)}")
            return []
        
        
    async def _ensure_collection_exists(self, collection_name: str = None) -> None:
        """Ensure that the collection exists in Qdrant.
        
        Args:
            collection_name: Optional collection name. If not provided, uses the default.
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
             
            # Check if collection exists
            collections = client.get_collections().collections
            collection_names = [collection.name for collection in collections]
            
            if collection_name not in collection_names:
                # Create collection with the schema
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "size": self.vector_size,
                        "distance": "Cosine"
                    }
                ) 
                
                logger.info(f"Created Qdrant collection: {collection_name}")
        except Exception as e:
            logger.error(f"Error ensuring Qdrant collection exists: {str(e)}")
            raise
    
    async def get_job_data(self, job_id: str, owner: str = None) -> Optional[str]:
        """
        Get job data from Qdrant.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job data as JSON string or None if not found
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # We need to search across all collections for this job_id
            collection_name = owner + self.source_collection_name
            
            # Query for query_criteria entry with the given job_id
            results = client.retrieve(
                collection_name=collection_name,
                ids=[job_id],
                with_vectors=False,
            )
            if results:
                # Extract query criteria from the payload
                job_data = results[0].payload
                    
                # Convert to JSON string
                return json.dumps(job_data)
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting job data for job {job_id} from Qdrant: {str(e)}")
            return None
    
    async def get_job_type(self, job_id: str, owner: str = None) -> Optional[str]:
        """
        Get job type from Qdrant.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job type or None if not found
        """
        try:
            return JobType.EMBEDDING.value
        except Exception as e:
            logger.error(f"Error getting job type for job {job_id} from Qdrant: {str(e)}")
            return None
    
    async def store_job_results(self, job_id: str, results: Dict[str, Any], owner: str = None, expiration: int=None) -> None:
        """
        Store job results in Qdrant.
        
        Args:
            job_id: Job ID
            results: Job results 
        """
        try:
            # Extract owner from results if available
            collection_name = owner + self.target_collection_name
            await self._ensure_collection_exists(collection_name)

            for result in results:
                embeddings = result.get("embeddings", [])
                extra_data = result.get("extra_data", {}) 
                
                # Save embeddings using the QdrantClientManager
                await qdrant_client.save_embeddings(
                    job_id=job_id,
                    embeddings=embeddings,
                    collection_name=collection_name,
                    extra_data=extra_data
                )
            logger.info(f"Stored job results for job {job_id} in Qdrant collection {collection_name}")
        except Exception as e:
            logger.error(f"Error storing job results for job {job_id} in Qdrant: {str(e)}")
            raise
    
    async def update_job_status(self, job_id: str, status: str, owner:str ,expiration: int = 60 * 60) -> None:
        """
        Update job status in Qdrant.
        
        Args:
            job_id: Job ID
            status: Job status
            expiration: Expiration time in seconds (default: 1 hour) - not used in Qdrant
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # We need to search across all collections for this job_id
            collection_name = owner + self.source_collection_name
            
            try:
                # Check if job_id exists in this collection
                results = client.retrieve(
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
                    client.set_payload(
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
            logger.error(f"Error updating job status for job {job_id} in Qdrant: {str(e)}")
            raise
    
    async def store_job_error(self, job_id: str, error: str, expiration: int = 60 * 60 * 24) -> None:
        """
        Store job error in Qdrant.
        
        Args:
            job_id: Job ID
            error: Error message
            expiration: Expiration time in seconds (default: 24 hours) - not used in Qdrant
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # We need to search across all collections for this job_id
            collections = client.get_collections().collections
            collection_names = [collection.name for collection in collections if collection.name.endswith(self.source_collection_name)]
            
            for collection_name in collection_names:
                
                try:
                    # Find all points with the given job_id in this collection
                    results = client.search(
                        collection_name=collection_name,
                        query_filter={"key": "job_id", "match": {"value": job_id}},
                        limit=100  # Assuming there won't be more than 100 entries for a job
                    )
                    
                    # Update error for all entries
                    for result in results:
                        point_id = result.id
                        
                        # Update the error field
                        client.set_payload(
                            collection_name=collection_name,
                            payload={
                                "error": error,
                                "status": "failed"
                            },
                            points=[point_id]
                        )
                    
                    if results:
                        logger.info(f"Stored job error for job {job_id} in collection {collection_name}")
                        return
                except Exception as e:
                    # Skip if collection doesn't exist or other issues
                    logger.warning(f"Skip if collection doesn't exist or other issues job {job_id} in Qdrant: {str(e)}")
                    continue
            
            logger.warning(f"Could not find job {job_id} in any collection to store error")
        except Exception as e:
            logger.error(f"Error storing job error for job {job_id} in Qdrant: {str(e)}")
            raise


    async def get_pending_jobs(self) -> List[str]:
        """
        Get pending jobs from Qdrant across all user collections.
        
        Returns:
            List of pending Job objects
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # Get all collections that match the pattern
            collections = client.get_collections().collections
            email_collections = [collection.name for collection in collections if collection.name.endswith(self.source_collection_name)]
            
            pending_jobs = []
            job_ids = set()  # Use a set to deduplicate job IDs
            
            # Search each collection for pending jobs
            for collection_name in email_collections:
                try:
                    owner = collection_name.replace(self.source_collection_name, "")

                    # Query for entries with analysis_status="pending"
                    results, next_page_offset = client.scroll(
                        collection_name=collection_name,
                        scroll_filter={
                            "must": [
                                {"key": "analysis_status", "match": {"value": "pending"}}, 
                            ]
                        },
                        with_payload=["id", "analysis_status", "type"],
                        with_vectors=False,
                        limit=1  # Limit to 5 pending jobs per collection
                    )
                    
                    # Extract job IDs and format as Job objects
                    # Extract job IDs and format as Redis-compatible keys
                    for point in results:
                        job_id = point.id
                        if job_id and job_id not in job_ids:
                            job_ids.add(job_id)
                            pending_jobs.append(f"sharepoint:{job_id}:{owner}")
                    # logger.info(f"Found {len(results)} pending jobs in collection {collection_name}")
                except Exception as e:
                    logger.error(f"Error querying collection {collection_name}: {str(e)}")
                    continue
            
            return pending_jobs
        except Exception as e:
            logger.error(f"Error getting pending jobs from Qdrant: {str(e)}")
            return []
 
    async def get_job_status(self, job: Job) -> Optional[str]:
        """
        Get job status from Qdrant.
        
        Args:
            job: Job object
            
        Returns:
            Job status or None if not found
        """
        try: 
            
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            collection_name = job.owner + self.source_collection_name
            
            # Query for any entry with the given job_id
            results = await client.retrieve(
                collection_name=collection_name,
                ids=[job.id],
                with_payload=["job_id", "analysis_status", "type"],
                with_vectors=False,
            )
            
            if results:
                # Return the status of the entry
                return results[0].payload.get("analysis_status")
            return None
        except Exception as e:
            logger.error(f"Error getting job status for job {job.id} from Qdrant: {str(e)}")
            return None

    async def store_query_criteria(self, job_id: str, owner: str, query_criteria: Dict[str, Any]) -> str:
        """
        Store query criteria in Qdrant.
        
        Args: 
            job_id: Job ID
            owner: Owner email address
            query_criteria: Query criteria
            
        Returns:
            Point ID of the stored query criteria
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # Get the collection name for this owner
            collection_name = self._get_email_collection_name(owner)
            
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
            
            # Store the query criteria entry
            client.upsert(
                collection_name=collection_name,
                points=[
                    {
                        "id": point_id,
                        "vector": dummy_vector,
                        "payload": query_entry.model_dump()
                    }
                ]
            )
            
            logger.info(f"Stored query criteria for job {job_id} in Qdrant")
            return point_id
        except Exception as e:
            logger.error(f"Error storing query criteria for job {job_id} in Qdrant: {str(e)}")
            raise
    
    async def store_analysis_results(self, job_id: str, analysis: EmailAnalysis, owner: str) -> str:
        """
        Store analysis results in Qdrant.
        
        Args: 
            job_id: Job ID
            analysis: Email analysis
            owner: Owner email address
            
        Returns:
            Point ID of the stored analysis results
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # Get the collection name for this owner
            collection_name = self._get_email_collection_name(owner)
            
            # Ensure collection exists
            await self._ensure_collection_exists(collection_name)
            
            # Create analysis chart entry using the Qdrant model
            analysis_chart = QdrantAnalysisChartEntry.from_email_analysis(
                analysis=analysis,
                job_id=job_id,
                owner=owner
            )
            
            # Create a dummy vector for now (in production, this would be an actual embedding)
            dummy_vector = [0.0] * self.vector_size
            
            # Generate a unique point ID
            point_id = f"{job_id}-analysis"
            
            # Store the analysis chart entry
            client.upsert(
                collection_name=collection_name,
                points=[
                    {
                        "id": point_id,
                        "vector": dummy_vector,
                        "payload": analysis_chart.model_dump()
                    }
                ]
            )
            
            logger.info(f"Stored analysis results for job {job_id} in Qdrant")
            return point_id
        except Exception as e:
            logger.error(f"Error storing analysis results for job {job_id} in Qdrant: {str(e)}")
            raise
    
    async def get_emails_by_job_id(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Get emails by job ID from Qdrant.
        
        Args:
            job_id: Job ID
            
        Returns:
            List of email entries
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # We need to search across all collections for this job_id
            collections = client.get_collections().collections
            collection_names = [collection.name for collection in collections if collection.name.endswith(self.source_collection_name)]
            
            emails = []
            
            for collection_name in collection_names: 
                
                # Query for email entries with the given job_id
                try:
                    results = client.search(
                        collection_name=collection_name,
                        query_filter={
                            "must": [
                                {"key": "job_id", "match": {"value": job_id}},
                                {"key": "type", "match": {"value": "email"}}
                            ]
                        },
                        limit=100  # Limit to 100 emails per job
                    )
                    
                    # Extract email entries
                    for result in results:
                        emails.append(result.payload)
                except:
                    # Skip if collection doesn't exist or other issues
                    continue
            
            return emails
        except Exception as e:
            logger.error(f"Error getting emails for job {job_id} from Qdrant: {str(e)}")
            return []
    
    async def get_analysis_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get analysis chart by job ID from Qdrant.
        
        Args:
            job_id: Job ID
            
        Returns:
            Analysis chart entry or None if not found
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # We need to search across all collections for this job_id
            collections = client.get_collections().collections
            collection_names = [collection.name for collection in collections if collection.name.endswith(self.source_collection_name)]
            
            for collection_name in collection_names:
                
                # Query for analysis chart entry with the given job_id
                try:
                    results = client.search(
                        collection_name=collection_name,
                        query_filter={
                            "must": [
                                {"key": "job_id", "match": {"value": job_id}},
                                {"key": "type", "match": {"value": "analysis_chart"}}
                            ]
                        },
                        limit=1
                    )
                    
                    if results:
                        # Return the analysis chart entry
                        return results[0].payload
                except:
                    # Skip if collection doesn't exist or other issues
                    continue
                
            return None
        except Exception as e:
            logger.error(f"Error getting analysis chart for job {job_id} from Qdrant: {str(e)}")
            return None

    async def claim_job(self, job_id: str, owner: str, ttl_seconds: int = 60 * 5) -> bool:
        """
        Atomically claim a job for processing.
        
        Args:
            job_id: The ID of the job to claim
            owner: The owner of the job
            ttl_seconds: Time-to-live for the claim in seconds (default: 5 minutes)
            
        Returns:
            bool: True if the job was successfully claimed, False otherwise
        """
        try:
            # Create the job key
            job_key = f"job:{job_id}:{owner}"
            
            # Check the current status
            current_status = await self.redis.get(f"{job_key}:status")
            
            # Only claim if the job is in 'pending' status
            if current_status and current_status.decode() != "pending":
                return False
                
            # Try to atomically claim the job using a Redis transaction
            tr = self.redis.multi_exec()
            
            # Set a lock with expiration
            tr.set(f"{job_key}:lock", "1", expire=ttl_seconds, exist='SET_IF_NOT_EXISTS')
            
            # Execute the transaction
            results = await tr.execute()
            
            # Check if the lock was acquired (first result will be True if successful)
            return bool(results[0])
            
        except Exception as e:
            from loguru import logger
            logger.error(f"Error claiming job {job_id} for {owner}: {str(e)}")
            return False
