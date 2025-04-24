#!/usr/bin/env python3
"""
Milvus client module for the Mail Analysis API.
"""

import asyncio
import time
from typing import Optional, Dict, List, Any
import uuid
from loguru import logger
from pymilvus import (
    connections, 
    Collection, 
    CollectionSchema, 
    FieldSchema, 
    DataType,
    utility
)

from app.core.config import config
from app.core.const import DENSE_EMBEDDING_NAME, SPARSE_FLOAT_VECTOR_NAME


class MilvusClientManager:
    """Singleton manager for Milvus client connection."""
    
    _instance = None
    _client = None
    _lock = asyncio.Lock()
    _retry_count = 3
    _retry_delay = 1
    _connected = False
    _collections_cache = {}
    _collections_cache_time = 0
    _collections_cache_ttl = 300  # 5 minutes
    
    def __new__(cls, *args, **kwargs):
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super(MilvusClientManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize Milvus client manager."""
        # Skip initialization if already initialized
        if self._client is not None:
            return
        
        # Get Milvus configuration from app config
        milvus_config = config.get("milvus", {})
        self.host = milvus_config.get("host", "localhost")
        self.port = milvus_config.get("port", 19530)
        self.user = milvus_config.get("user", "")
        self.password = milvus_config.get("password", "")
        self.api_key = milvus_config.get("api_key", "")
        self.timeout = milvus_config.get("timeout", 30)
    
    async def connect(self) -> bool:
        """
        Connect to Milvus server.
        
        Returns:
            bool: True if connected successfully, False otherwise
        """
        if self._connected:
            return True
        
        try:
 
 
            connections.connect(uri=self.host,
                                token=self.api_key)
 
            # Test the connection
            utility.has_collection("_test_connection")
            
            self._connected = True
            logger.info(f"Connected to Milvus at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Error connecting to Milvus: {str(e)}")
            self._connected = False
            return False
    
    async def ping(self) -> bool:
        """
        Ping Milvus server to check connectivity.
        
        Returns:
            bool: True if ping successful, False otherwise
        """
        try:
            if not self._connected:
                await self.connect()
            
            # Test the connection with a simple operation
            utility.has_collection("_ping_test")
            return True
        except Exception as e:
            logger.error(f"Error pinging Milvus: {str(e)}")
            self._connected = False
            return False
    
    async def connect_with_retry(self) -> None:
        """Connect to Milvus with retry logic."""
        for attempt in range(self._retry_count):
            if await self.connect():
                return
            
            # Wait before retrying
            await asyncio.sleep(self._retry_delay * (attempt + 1))
        
        # If we reach here, all attempts failed
        raise ConnectionError(f"Failed to connect to Milvus at {self.host}:{self.port} after {self._retry_count} attempts")
    
    async def get_collections(self) -> List[str]:
        """
        Get all collections with caching to reduce server calls.
        
        Returns:
            List of collection names
        """
        try:
            current_time = time.time()
            
            # Return cached collections if not expired
            if self._collections_cache and (current_time - self._collections_cache_time < self._collections_cache_ttl):
                logger.debug("Using cached collections")
                return list(self._collections_cache.keys())
            
            # Connect to Milvus
            await self.connect_with_retry()
            
            # Get collections
            collection_names = utility.list_collections()
            
            # Update cache
            self._collections_cache = {name: current_time for name in collection_names}
            self._collections_cache_time = current_time
            
            logger.debug(f"Updated collections cache with {len(collection_names)} collections")
            return collection_names
        except Exception as e:
            # If we have a cache, return it even if expired rather than failing
            if self._collections_cache:
                logger.warning(f"Error getting collections, using expired cache: {str(e)}")
                return list(self._collections_cache.keys())
            
            logger.error(f"Error getting collections: {str(e)}")
            return []
    
    async def ensure_collection_exists(self, collection_name: str, vector_size: int = 1536) -> bool:
        """
        Ensure that a collection exists in Milvus, creating it if it doesn't.
        
        Args:
            collection_name: The name of the collection
            vector_size: Size of the vector embeddings (default: 1536 for OpenAI embeddings)
            
        Returns:
            bool: True if collection exists or was created, False otherwise
        """
        try:
            # Connect to Milvus
            await self.connect_with_retry()
            
            # Check if collection exists
            if utility.has_collection(collection_name):
                return True
            
            # Collection doesn't exist, create it
            # Define fields for the collection
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=100),
                FieldSchema(name="dense", dtype=DataType.FLOAT_VECTOR, dim=vector_size),
                FieldSchema(name="sparse", dtype=DataType.SPARSE_FLOAT_VECTOR),
                FieldSchema(name="job_id", dtype=DataType.VARCHAR, max_length=100),  
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535), 
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="metadata", dtype=DataType.JSON),
                FieldSchema(name="sensitivity", dtype=DataType.VARCHAR, max_length=50),  
            ]
            
            # Create collection schema with enable_dynamic_field=True to accept unknown fields
            schema = CollectionSchema(
                fields=fields, 
                description=f"Mail Analysis collection: {collection_name}",
                enable_dynamic_field=True
            )
            
            # Create collection
            collection = Collection(name=collection_name, schema=schema)
            
            # Create an IVF_FLAT index for vector field
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024}
            }
            collection.create_index(field_name="dense", index_params=index_params)
            
            collection.create_index(field_name="sparse", index_name="sparse_index")
            
            # Create index on sensitivity field for better query performance
            collection.create_index(field_name="sensitivity", index_name="sensitivity_index")
            
            logger.info(f"Created Milvus collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error ensuring Milvus collection exists: {str(e)}")
            return False
    
    async def save_embeddings(self, job_id: str, embeddings: list, collection_name: str, 
                             extra_data: dict = None) -> dict:
        """
        Save embeddings to Milvus.
        
        Args:
            job_id: Job ID
            embeddings: List of embeddings to save
            collection_name: Name of the collection to save to
            metadata: Optional metadata about the job
            extra_data: Optional extra data to store with the embeddings
            
        Returns:
            Dict containing status and information about the save operation
        """
        try:
            # Connect to Milvus
            await self.connect_with_retry()
            
            # Ensure collection exists
            collection_exists = await self.ensure_collection_exists(
                collection_name=collection_name,
                vector_size=len(embeddings[0][DENSE_EMBEDDING_NAME][0])
            )
            
            if not collection_exists:
                return {
                    "saved": False,
                    "error": f"Failed to ensure collection {collection_name} exists"
                }
            
            # Create a list of entities to insert
            entities = []
            ids = []
            
            for embedding_item in embeddings:
                # Generate a unique ID for each embedding
                point_id = uuid.uuid4().hex
                ids.append(point_id)
                
                # Get the dense embedding vector
                dense_embedding = embedding_item[DENSE_EMBEDDING_NAME][0]
                sparse_embedding = embedding_item[SPARSE_FLOAT_VECTOR_NAME]

                # Prepare entity data
                entity = {
                    "id": point_id,
                    "dense": dense_embedding,
                    "sparse": sparse_embedding,
                    "job_id": job_id,  
                    "content": embedding_item["content"],
                    "chunk_index": embedding_item["chunk_index"],
                    "sensitivity": extra_data["sensitivity"] if extra_data and "sensitivity" in extra_data else None
                }
                
                # Handle metadata properly for JSON field
                if extra_data is None:
                    entity["metadata"] = {}
                else:
                    # Ensure extra_data is a dictionary
                    if isinstance(extra_data, dict):
                        entity["metadata"] = extra_data
                    else:
                        # Convert to dict if possible, otherwise use empty dict
                        try:
                            entity["metadata"] = dict(extra_data)
                        except (TypeError, ValueError):
                            logger.warning(f"Could not convert extra_data to dictionary. Using empty dict instead.")
                            entity["metadata"] = {}
                
                entities.append(entity)
            
            # Get the collection
            collection = Collection(name=collection_name)
            collection.load()
            
            # Insert the entities
            insert_result = collection.insert(entities)
            collection.flush()
            
            logger.info(f"Saved {len(entities)} embeddings to Milvus collection {collection_name} for job {job_id}")
            
            return {
                "saved": True,
                "collection": collection_name,
                "points": len(entities)
            }
            
        except Exception as e:
            logger.error(f"Error saving embeddings to Milvus: {str(e)}")
            return {
                "saved": False,
                "error": str(e)
            }
    
    async def search(self, collection_name: str, query_vector: List[float], limit: int = 10,
                    filter_expr: str = None) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in Milvus.
        
        Args:
            collection_name: Name of the collection to search
            query_vector: Query vector
            limit: Maximum number of results to return
            filter_expr: Optional filter expression
            
        Returns:
            List of search results
        """
        try:
            # Connect to Milvus
            await self.connect_with_retry()
            
            # Check if collection exists
            if not utility.has_collection(collection_name):
                return []
            
            # Get the collection
            collection = Collection(name=collection_name)
            collection.load()
            
            # Search parameters
            search_params = {
                "metric_type": "COSINE",
                "params": {"nprobe": 10}
            }
            
            # Perform search
            if filter_expr:
                results = collection.search(
                    data=[query_vector],
                    anns_field="vector",
                    param=search_params,
                    limit=limit,
                    expr=filter_expr,
                    output_fields=["job_id", "analysis_status", "type", "content", "chunk_index"]
                )
            else:
                results = collection.search(
                    data=[query_vector],
                    anns_field="vector",
                    param=search_params,
                    limit=limit,
                    output_fields=["job_id", "analysis_status", "type", "content", "chunk_index"]
                )
            
            # Format results
            formatted_results = []
            for hits in results:
                for hit in hits:
                    result = {
                        "id": hit.id,
                        "distance": hit.distance,
                        "payload": hit.entity.to_dict()
                    }
                    formatted_results.append(result)
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error searching Milvus collection {collection_name}: {str(e)}")
            return []
    
    async def retrieve(self, collection_name: str, ids: List[str], with_vectors: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve entities by IDs.
        
        Args:
            collection_name: Name of the collection
            ids: List of entity IDs to retrieve
            with_vectors: Whether to include vectors in the result
            
        Returns:
            List of retrieved entities
        """
        try:
            # Connect to Milvus
            await self.connect_with_retry()
            
            # Check if collection exists
            if not utility.has_collection(collection_name):
                return []
            
            # Get the collection
            collection = Collection(name=collection_name)
            collection.load()
            
            # Define output fields
            output_fields = ["job_id", "analysis_status", "type", "content", "chunk_index", "lastAnalysisUpdate"]
            if with_vectors:
                output_fields.append("vector")
            
            # Retrieve entities
            expr = f'id in ["{ids[0]}"'
            for id in ids[1:]:
                expr += f', "{id}"'
            expr += ']'
            
            results = collection.query(
                expr=expr,
                output_fields=output_fields
            )
            
            # Format results to match Qdrant's format
            formatted_results = []
            for result in results:
                payload = {k: v for k, v in result.items() if k != "vector"}
                formatted_result = {
                    "id": result["id"],
                    "payload": payload
                }
                if with_vectors and "vector" in result:
                    formatted_result["vector"] = result["vector"]
                
                formatted_results.append(formatted_result)
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error retrieving entities from Milvus collection {collection_name}: {str(e)}")
            return []
    
    async def set_payload(self, collection_name: str, payload: Dict[str, Any], points: List[str]) -> bool:
        """
        Update payload for specific points using upsert.
        
        Args:
            collection_name: Name of the collection
            payload: Payload data to update (key-value pairs)
            points: List of point IDs (primary keys) to update
            
        Returns:
            bool: True if updated successfully, False otherwise
        """
        try:
            # Connect to Milvus
            await self.connect_with_retry()
            
            # Check if collection exists
            if not utility.has_collection(collection_name):
                logger.warning(f"Collection {collection_name} does not exist.")
                return False
            
            # Get the collection
            collection = Collection(name=collection_name)
            collection.load() # Ensure collection is loaded for operations

            # Prepare data for upsert
            # Upsert expects a list of dictionaries or a dictionary of lists.
            # Let's use a list of dictionaries, one for each point to update.
            upsert_data = []
            for point_id in points:
                entity_data = {"pk": point_id} # Include the primary key
                entity_data.update(payload) # Add the fields to update
                upsert_data.append(entity_data)

            if not upsert_data:
                logger.warning("No data prepared for upsert.")
                return False

            # Perform the upsert operation
            mutation_result = collection.upsert(data=upsert_data)
            
            # Check if upsert was successful (optional, based on API)
            # You might need to inspect mutation_result for success/failure details
            if mutation_result.upsert_count != len(points):
                 logger.warning(f"Upsert operation might not have updated all points. Expected: {len(points)}, Actual: {mutation_result.upsert_count}")
                 # Decide if this is an error or just a warning

            collection.flush() # Ensure changes are persisted
            
            logger.info(f"Successfully upserted payload for {len(points)} points in collection {collection_name}.")
            return True
            
        except Exception as e:
            logger.error(f"Error upserting payload in Milvus collection {collection_name}: {str(e)}")
            # Log the exception traceback for more details
            logger.exception(e)
            return False
    
    async def scroll(self, collection_name: str, scroll_filter: str = None, 
                   with_payload: List[str] = None, with_vectors: bool = False, 
                   limit: int = 10, offset: str = None) -> tuple:
        """
        Scroll through records in a collection.
        
        Args:
            collection_name: Name of the collection
            scroll_filter: Optional filter expression
            with_payload: List of payload fields to include
            with_vectors: Whether to include vectors in the result
            limit: Maximum number of results to return
            offset: Pagination offset
            
        Returns:
            Tuple of (results, next_offset)
        """
        try:
            # Connect to Milvus
            await self.connect_with_retry()
            
            # Check if collection exists
            if not utility.has_collection(collection_name):
                return [], None
            
            # Get the collection
            collection = Collection(name=collection_name)
            collection.load()
            
            # Define output fields
            output_fields = ["pk"]
            if with_payload:
                output_fields.extend(with_payload)
            if with_vectors:
                output_fields.append("vector")
            
            # Determine the offset (simple pagination for now)
            current_offset = 0
            if offset:
                try:
                    current_offset = int(offset)
                except:
                    current_offset = 0
            
            # Query based on filter
            if scroll_filter:
                results = collection.query(
                    expr=scroll_filter,
                    output_fields=output_fields,
                    limit=limit,
                    offset=current_offset
                )
            else:
                results = collection.query(
                    expr="pk != ''",  # Match all
                    output_fields=output_fields,
                    limit=limit,
                    offset=current_offset
                )
            
            # Format results to match Qdrant's format
            formatted_results = []
            for result in results:
                payload = {k: v for k, v in result.items() if k not in ["pk", "vector"]}
                formatted_result = {
                    "pk": result["pk"],
                    "payload": payload
                }
                if with_vectors and "vector" in result:
                    formatted_result["vector"] = result["vector"]
                
                formatted_results.append(formatted_result)
            
            # Calculate next offset
            next_offset = None
            if len(results) == limit:
                next_offset = str(current_offset + limit)
            
            return formatted_results, next_offset
        except Exception as e:
            logger.error(f"Error scrolling through Milvus collection {collection_name}: {str(e)}")
            return [], None
    
    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection.
        
        Args:
            collection_name: Name of the collection to delete
            
        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            # Connect to Milvus
            await self.connect_with_retry()
            
            # Check if collection exists
            if not utility.has_collection(collection_name):
                return True  # Already doesn't exist
            
            # Delete collection
            utility.drop_collection(collection_name)
            
            # Remove from cache
            if collection_name in self._collections_cache:
                del self._collections_cache[collection_name]
            
            logger.info(f"Deleted Milvus collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting Milvus collection {collection_name}: {str(e)}")
            return False


# Create singleton instance
milvus_client = MilvusClientManager()