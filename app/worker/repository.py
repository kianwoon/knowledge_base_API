#!/usr/bin/env python3
"""Repository implementations for the Worker module."""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from app.core.const import JobType
from app.core.redis import redis_client
from app.core.qdrant import qdrant_client
from app.worker.interfaces import JobRepository
from app.core.config import localize_datetime
from app.models.qdrant_mail import QdrantEmailEntry, QdrantQueryCriteria, QdrantQueryCriteriaEntry, QdrantAnalysisChartEntry
from app.models.email import EmailSchema, EmailAnalysis
from qdrant_client.http import models

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    
    def default(self, obj):
        if isinstance(obj, datetime):
            # Ensure datetime has timezone info before converting to ISO format
            if obj.tzinfo is None:
                obj = localize_datetime(obj)
            return obj.isoformat()
        return super().default(obj)


class RedisJobRepository(JobRepository):
    """Redis implementation of the JobRepository interface."""
    
    async def ping(self) -> None:
        """Ping the Redis server to check connectivity."""
        try:
            await redis_client.connect()
        except Exception as e:
            logger.error(f"Error pinging Redis: {str(e)}")
            raise
    
    async def connect_with_retry(self) -> None:
        """Connect to Redis with retry logic."""
        try:
            await redis_client.connect_with_retry()
        except Exception as e:
            logger.error(f"Error connecting to Redis: {str(e)}")
            raise

    async def get_job_data(self, job_id: str) -> Optional[str]:
        """
        Get job data from Redis.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job data as JSON string or None if not found
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect_with_retry()
            return await redis_client.get(f"job:{job_id}:data")
        except Exception as e:
            logger.error(f"Error getting job data for job {job_id}: {str(e)}")
            return None
    

    async def get_job_type(self, job_id: str) -> Optional[str]:
        """
        Get job type from Redis.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job type or None if not found
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect_with_retry()
            return await redis_client.get(f"job:{job_id}:type")
        except Exception as e:
            logger.error(f"Error getting job type for job {job_id}: {str(e)}")
            return None
    
    async def store_job_results(self, job_id: str, results: Dict[str, Any], expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Store job results in Redis.
        
        Args:
            job_id: Job ID
            results: Job results
            expiration: Expiration time in seconds (default: 7 days)
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect_with_retry()
            await redis_client.setex(
                f"job:{job_id}:results",
                expiration,
                json.dumps(results, cls=DateTimeEncoder)
            )
        except Exception as e:
            logger.error(f"Error storing job results for job {job_id}: {str(e)}")
            raise
    
    async def update_job_status(self, job_id: str, status: str, expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Update job status in Redis.
        
        Args:
            job_id: Job ID
            status: Job status
            expiration: Expiration time in seconds (default: 7 days)
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect_with_retry()
            await redis_client.setex(
                f"job:{job_id}:status",
                expiration,
                status
            )
        except Exception as e:
            logger.error(f"Error updating job status for job {job_id}: {str(e)}")
            raise
    
    async def store_job_error(self, job_id: str, error: str, expiration: int = 60 * 60 * 24) -> None:
        """
        Store job error in Redis.
        
        Args:
            job_id: Job ID
            error: Error message
            expiration: Expiration time in seconds (default: 24 hours)
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect()
            await redis_client.setex(
                f"job:{job_id}:error",
                expiration,
                error
            )
        except Exception as e:
            logger.error(f"Error storing job error for job {job_id}: {str(e)}")
            raise
    
    async def get_job_id(self, job_key):
        return await super().get_job_id(job_key)
    

    async def get_pending_jobs(self) -> List[str]:
        """
        Get pending jobs from Redis.
        
        Returns:
            List of pending job keys
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect()
            return await redis_client.scan("job:*:status")
        except Exception as e:
            logger.error(f"Error getting pending jobs: {str(e)}")
            return []

    async def get_pending_jobs_lua(self) -> List[str]:
        """
        Get pending jobs from Redis using Lua script.
        
        Returns:
            List of pending job keys
        """
        try:
            # Ensure Redis connection is active
            await redis_client.connect()
            script = """
                local cursor = "0"
                local pending_jobs = {}
                repeat
                    local result = redis.call('scan', cursor, 'match', 'job:*:status')
                    cursor = result[1]
                    local keys = result[2]
                    for i = 1, #keys do
                        local key = keys[i]
                        if redis.call('get', key) == 'pending' then
                            table.insert(pending_jobs, key)
                        end
                    end
                until cursor == "0"
                return pending_jobs
            """
            return await redis_client.eval(script,keys=[], args=[])
        except Exception as e:
            logger.error(f"Error getting pending jobs with Lua script: {str(e)}")
            return []

    async def get_job_status(self, job_key: str) -> Optional[str]:
        """
        Get job status from Redis.
        
        Args:
            job_key: Job key
            
        Returns:
            Job status or None if not found
        """
        try:
            return await redis_client.get(job_key)
        except Exception as e:
            logger.error(f"Error getting job status for key {job_key}: {str(e)}")
            return None


class QdrantJobRepository(JobRepository):
    """Qdrant implementation of the JobRepository interface.
    
    This implementation stores job data in a Qdrant vector database according to the
    schema defined in qdrant_email_knowledge_full_schema.md.
    """
    
    def __init__(self, collection_name: str = "email_knowledge", vector_size: int = 1536):
        """Initialize QdrantJobRepository.
        
        Args:
            collection_name: Qdrant collection name (default: email_knowledge)
            vector_size: Size of the vector embeddings (default: 1536 for OpenAI embeddings)
        """
        self.collection_name = collection_name
        self.vector_size = vector_size
    
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

    async def _ensure_collection_exists(self) -> None:
        """Ensure that the collection exists in Qdrant."""
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # Check if collection exists
            collections = client.get_collections().collections
            collection_names = [collection.name for collection in collections]
            
            if self.collection_name not in collection_names:
                # Create collection with the schema from qdrant_email_knowledge_full_schema.md
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        "size": self.vector_size,
                        "distance": "Cosine"
                    }
                )
                
                # Create payload schema - common fields
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="type",
                    field_schema="keyword"
                )
                
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="job_id",
                    field_schema="keyword"
                )
                
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="owner",
                    field_schema="keyword"
                )
                
                # Create payload schema - email specific fields
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="sender",
                    field_schema="keyword"
                )
                
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="subject",
                    field_schema="text"
                )
                
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="date",
                    field_schema="keyword"
                )
                
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="folder",
                    field_schema="keyword"
                )
                
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="tags",
                    field_schema="keyword"
                )
                
                client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="status",
                    field_schema="keyword"
                )
                
                logger.info(f"Created Qdrant collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error ensuring Qdrant collection exists: {str(e)}")
            raise
    
    async def get_job_data(self, job_id: str) -> Optional[str]:
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
            
            # Ensure collection exists
            await self._ensure_collection_exists()
            
            # Query for query_criteria entry with the given job_id
            results = client.retrieve(
                    collection_name=self.collection_name,
                    ids=[job_id],
                    with_vectors=False,
                )
            if not results:
                return None
                
            # Extract query criteria from the payload
            job_data = results[0].payload
            
            # Convert to JSON string
            return json.dumps(job_data)
        except Exception as e:
            logger.error(f"Error getting job data for job {job_id} from Qdrant: {str(e)}")
            return None
    
    async def get_job_type(self, job_id: str) -> Optional[str]:
        """
        Get job type from Qdrant.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job type or None if not found
        """
        return JobType.EMBEDDING.value
        
    
    async def store_job_results(self, job_id: str, result: Dict[str, Any], expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Store job results in Qdrant.
        
        Args:
            job_id: Job ID
            results: Job results
            expiration: Expiration time in seconds (default: 7 days) - not used in Qdrant
        """
        try:
 
            # Save embeddings to Qdrant using the QdrantClientManager
            embeddings = result.get("embeddings", [])
            metadata = result.get("_metadata", {})
            job_data = result.get("job_data", {})
            extra_data = {
                "subject": job_data.get("subject", ""),
                "date": job_data.get("date", ""),
                "sender": job_data.get("sender", ""),
                "recipient": job_data.get("recipient", "")
            }
            
            # Save embeddings using the QdrantClientManager
            await qdrant_client.save_embeddings(
                job_id=job_id,
                embeddings=embeddings,
                metadata=metadata,
                extra_data=extra_data
            )      
            
            logger.info(f"Stored job results for job {job_id} in Qdrant")
        except Exception as e:
            logger.error(f"Error storing job results for job {job_id} in Qdrant: {str(e)}")
            raise
    
    async def update_job_status(self, job_id: str, status: str, expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Update job status in Qdrant.
        
        Args:
            job_id: Job ID
            status: Job status
            expiration: Expiration time in seconds (default: 7 days) - not used in Qdrant
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # Ensure collection exists
            await self._ensure_collection_exists()
            
                            # Update the status field
            client.set_payload(
                    collection_name=self.collection_name,
                    payload={"analysis_status": status},
                    points=[job_id]
                ) 
            
            logger.info(f"Updated job status for job {job_id} in Qdrant to {status}")
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
            
            # Ensure collection exists
            await self._ensure_collection_exists()
            
            # Find all points with the given job_id
            results = client.search(
                collection_name=self.collection_name,
                query_filter={"key": "job_id", "match": {"value": job_id}},
                limit=100  # Assuming there won't be more than 100 entries for a job
            )
            
            # Update error for all entries
            for result in results:
                point_id = result.id
                
                # Update the error field
                client.set_payload(
                    collection_name=self.collection_name,
                    payload={
                        "error": error,
                        "status": "failed"
                    },
                    points=[point_id]
                )
            
            logger.info(f"Stored job error for job {job_id} in Qdrant")
        except Exception as e:
            logger.error(f"Error storing job error for job {job_id} in Qdrant: {str(e)}")
            raise
    
    async def get_pending_jobs(self) -> List[str]:
        """
        Get pending jobs from Qdrant.
        
        Returns:
            List of pending job keys in the format "job:{job_id}:status"
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # Ensure collection exists
            await self._ensure_collection_exists()
            
            # Query for entries with analysis_status="pending"
            results, next_page_offset = client.scroll(
                collection_name=self.collection_name,
                scroll_filter={
                    "must": [
                        {"key": "analysis_status", "match": {"value": "pending"}},
                        {"key": "type", "match": {"value": "email"}}
                    ]
                },
                with_payload=["job_id", "analysis_status", "type"],
                with_vectors=False,
                limit=1  # Limit to 10 pending jobs at a time
            )
            
            # Extract job IDs and format as Redis-compatible keys
            pending_jobs = []
            job_ids = set()  # Use a set to deduplicate job IDs
            
            for point in results:
                job_id = point.id
                if job_id and job_id not in job_ids:
                    job_ids.add(job_id)
                    pending_jobs.append(f"job:{job_id}:status")
            
            return pending_jobs
        except Exception as e:
            logger.error(f"Error getting pending jobs from Qdrant: {str(e)}")
            return []
    
    async def get_job_status(self, job_key: str) -> Optional[str]:
        """
        Get job status from Qdrant.
        
        Args:
            job_key: Job key in the format "job:{job_id}:status"
            
        Returns:
            Job status or None if not found
        """
        try:
            # Extract job ID from the key
            job_id = job_key.split(":")[1] if ":" in job_key else job_key
            
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # Ensure collection exists
            await self._ensure_collection_exists()
            
            # Query for any entry with the given job_id
            # results = client.query_points(
            #     collection_name=self.collection_name,
            #     query=str(job_id), 
            # )
            
            results = client.retrieve(
                    collection_name=self.collection_name,
                    ids=[job_id],
                    with_payload=["job_id", "analysis_status", "type"],
                    with_vectors=False,
                )
  
 
            if not results:
                return None
                
            # Return the status of the entry
            return results[0].payload.get("analysis_status")
        except Exception as e:
            logger.error(f"Error getting job analysis_status for key {job_key} from Qdrant: {str(e)}")
            return None


    async def store_email(self, email: EmailSchema, job_id: str, owner: str, folder: str = "Inbox") -> str:
        """
        Store email in Qdrant.
        
        Args:
            email: Email schema
            job_id: Job ID
            owner: Owner email address
            folder: Folder name (default: Inbox)
            
        Returns:
            Point ID of the stored email
        """
        try:
            # Connect to Qdrant
            client = await qdrant_client.connect_with_retry()
            
            # Ensure collection exists
            await self._ensure_collection_exists()
            
            # Create email entry using the Qdrant model
            email_entry = QdrantEmailEntry.from_email_schema(
                email=email,
                job_id=job_id,
                owner=owner,
                folder=folder
            )
            
            # Create a dummy vector for now (in production, this would be an actual embedding)
            # In a real implementation, you would generate embeddings for the email content
            dummy_vector = [0.0] * self.vector_size
            
            # Generate a unique point ID
            point_id = f"{job_id}-email-{email.message_id}"
            
            # Store the email entry
            client.upsert(
                collection_name=self.collection_name,
                points=[
                    {
                        "id": point_id,
                        "vector": dummy_vector,
                        "payload": email_entry.model_dump()
                    }
                ]
            )
            
            logger.info(f"Stored email {email.message_id} for job {job_id} in Qdrant")
            return point_id
        except Exception as e:
            logger.error(f"Error storing email for job {job_id} in Qdrant: {str(e)}")
            raise
    
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
            
            # Ensure collection exists
            await self._ensure_collection_exists()
            
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
                collection_name=self.collection_name,
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
            
            # Ensure collection exists
            await self._ensure_collection_exists()
            
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
                collection_name=self.collection_name,
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
            
            # Ensure collection exists
            await self._ensure_collection_exists()
            
            # Query for email entries with the given job_id
            results = client.search(
                collection_name=self.collection_name,
                query_filter={
                    "must": [
                        {"key": "job_id", "match": {"value": job_id}},
                        {"key": "type", "match": {"value": "email"}}
                    ]
                },
                limit=100  # Limit to 100 emails per job
            )
            
            # Extract email entries
            emails = []
            for result in results:
                emails.append(result.payload)
            
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
            
            # Ensure collection exists
            await self._ensure_collection_exists()
            
            # Query for analysis chart entry with the given job_id
            results = client.search(
                collection_name=self.collection_name,
                query_filter={
                    "must": [
                        {"key": "job_id", "match": {"value": job_id}},
                        {"key": "type", "match": {"value": "analysis_chart"}}
                    ]
                },
                limit=1
            )
            
            if not results:
                return None
                
            # Return the analysis chart entry
            return results[0].payload
        except Exception as e:
            logger.error(f"Error getting analysis chart for job {job_id} from Qdrant: {str(e)}")
            return None
