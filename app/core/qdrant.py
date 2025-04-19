#!/usr/bin/env python3
"""
Qdrant client module for the Mail Analysis API.
"""

import asyncio
from typing import Optional
import uuid
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import config
from app.core.const import DENSE_EMBEDDING_NAME, BM25_EMBEDDING_NAME, LATE_INTERACTION_EMBEDDING_NAME


class QdrantClientManager:
    """Singleton manager for Qdrant client connection."""
    
    _instance: Optional["QdrantClientManager"] = None
    _client: Optional[QdrantClient] = None
    _collection_name: Optional[str] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(QdrantClientManager, cls).__new__(cls)
            cls._instance._client = None
            cls._instance._collection_name = None
        return cls._instance
    
    async def ping(self) -> None:
        """Ping the Qdrant server to check connectivity."""
        if self._client is None:
            raise Exception("Qdrant client not connected")
        
        try:
            # Ping the server
            self._client.get_collections()
            # logger.info("Qdrant server is reachable")
        except UnexpectedResponse as e:
            logger.error(f"Unexpected response from Qdrant server: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error pinging Qdrant server: {str(e)}")
            raise

    async def connect(self) -> QdrantClient:
        """Connect to Qdrant server."""
        if self._client is not None:
            return self._client
            
        # Get Qdrant configuration from settings
        qdrant_config = config.get("qdrant", {})
        host = qdrant_config.get("host", "localhost")
        port = qdrant_config.get("port", 6333)
        api_key = qdrant_config.get("api_key")
        timeout = qdrant_config.get("timeout", 10.0) 
        
        try:
            # Create Qdrant client
            self._client = QdrantClient(
                host=host,
                port=port,
                api_key=api_key,
                timeout=timeout
            )
            
            # Test connection
            self._client.get_collections()
            logger.info(f"Connected to Qdrant server at {host}:{port}")
            
            return self._client
        except Exception as e:
            logger.error(f"Error connecting to Qdrant server: {str(e)}")
            raise
    
    async def connect_with_retry(self, max_retries: int = 5, retry_delay: int = 5) -> QdrantClient:
        """Connect to Qdrant server with retry."""
        retries = 0
        last_error = None
        
        while retries < max_retries:
            try:
                return await self.connect()
            except Exception as e:
                last_error = e
                retries += 1
                logger.warning(f"Retry {retries}/{max_retries} connecting to Qdrant server")
                await asyncio.sleep(retry_delay)
        
        logger.error(f"Failed to connect to Qdrant server after {max_retries} retries")
        raise last_error or Exception("Failed to connect to Qdrant server")
    
    async def disconnect(self) -> None:
        """Disconnect from Qdrant server."""
        if self._client is not None:
            # Close client connection
            # self._client.close()
            self._client = None
            logger.info("Disconnected from Qdrant server")
    
    @property
    def client(self) -> QdrantClient:
        """Get Qdrant client."""
        if self._client is None:
            raise Exception("Qdrant client not connected")
        return self._client
        
    @property
    def collection_name(self) -> str:
        """Get Qdrant collection name."""
        if self._collection_name is None:
            # Get default from config if not already set
            qdrant_config = config.get("qdrant", {})
            self._collection_name = qdrant_config.get("collection_name", "email_knowledge")
        return self._collection_name
    
    async def save_embeddings(self, job_id: str, embeddings: list, collection_name: str, metadata: dict = None, extra_data: dict = None) -> dict:
        """
        Save embeddings to Qdrant.
        
        Args:
            job_id: Job ID
            embeddings: List of embedding items with 'chunk_index', 'embedding', and 'text'
            metadata: Additional metadata for the embeddings
            extra_data: Additional data to include in each point's payload
            
        Returns:
            Dict containing status of the save operation
        """
        try:
            # Get client and collection name
            client = await self.connect_with_retry() 
            
            if not embeddings:
                logger.warning(f"No embeddings to save for job {job_id}")
                return {
                    "saved": False,
                    "reason": "No embeddings provided"
                }
                
            # Create collection if it doesn't exist
            try:
                collections_list = client.get_collections().collections
                collection_names = [collection.name for collection in collections_list]
                dense_embeddings = embeddings[0][DENSE_EMBEDDING_NAME]
                late_interaction_embeddings = embeddings[0][LATE_INTERACTION_EMBEDDING_NAME]
                

                if collection_name not in collection_names:
                    logger.info(f"Creating collection {collection_name} for embeddings")

                    client.create_collection(
                        collection_name=collection_name,
                        vectors_config={
                            "dense": models.VectorParams(
                            size=len(dense_embeddings[0]),
                            distance=models.Distance.COSINE
                
                        ),
                         "colbertv2.0": models.VectorParams(
                            size=len(late_interaction_embeddings[0][0]),
                            distance=models.Distance.COSINE,
                            multivector_config=models.MultiVectorConfig(
                                comparator=models.MultiVectorComparator.MAX_SIM,
                            )
                        ),
                    },
                    sparse_vectors_config={
                        "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF, )
                    })
                    
                    logger.info(f"Created collection {collection_name} for embeddings")
                    
            except Exception as e:
                logger.error(f"Error checking/creating collection: {str(e)}")
                
            # Prepare points for Qdrant
            points = []
            for embedding_item in embeddings:
                # Generate a unique ID for each embedding
                point_id = uuid.uuid4().hex
                dense_embedding = embedding_item[DENSE_EMBEDDING_NAME][0]
                bm25_embedding = embedding_item[BM25_EMBEDDING_NAME][0]
                late_interaction_embedding = embedding_item[LATE_INTERACTION_EMBEDDING_NAME][0]


                # Create the point payload
                payload = {
                    "chunk_index": embedding_item["chunk_index"],
                    "content": embedding_item["content"],
                    "metadata": extra_data or {}
                }
                 
                points.append(models.PointStruct(
                    id=point_id,
                    vector= {
                        "dense": dense_embedding,
                        "bm25": bm25_embedding.as_object(),
                        "colbertv2.0": late_interaction_embedding,
                    },
                    payload=payload
                ))
            
            # Upsert points into the collection
            client.upsert(
                collection_name=collection_name,
                points=points
            )
            
            logger.info(f"Saved {len(points)} embeddings to Qdrant collection {collection_name} for job {job_id}")
            
            return {
                "saved": True,
                "collection": collection_name,
                "points": len(points)
            }
                
        except Exception as e:
            logger.error(f"Error saving embeddings to Qdrant: {str(e)}")
            return {
                "saved": False,
                "error": str(e)
            }


# Create singleton instance
qdrant_client = QdrantClientManager()