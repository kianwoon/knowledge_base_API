import time
from typing import Any, Dict, List

from loguru import logger

from app.utils.text_chunker import TextChunker 
from app.core.const import DENSE_EMBEDDING_NAME, SPARSE_FLOAT_VECTOR_NAME
import FlagEmbedding

from pymilvus.model.hybrid import BGEM3EmbeddingFunction
embedding_fn = BGEM3EmbeddingFunction(
    model_name='BAAI/bge-m3',  # Specify the model name
    device='cpu',  # Specify the device to use, 'cpu' is more stable
    use_fp16=False  # Set to False for CPU usage
)

# Don't initialize at module level - will be created per instance
# embedding_fn = BGEM3EmbeddingFunction()


class EmbeddingServiceMilvus():
    """Service for interacting with OpenAI API."""
    
    def __init__(self, text_chunker: TextChunker = None):   
        """Initialize OpenAI service.
        
        Args:
            key_manager: Key manager for API keys
            cost_tracker: Cost tracker for API usage
            text_chunker: Text chunker for splitting text into manageable pieces
        """
        self.text_chunker = text_chunker or TextChunker()
        # Initialize the embedding function in the instance

        
    async def embedding_text(self, text: str) -> list[Any]:


        """Get embedding for text using OpenAI API.
        
        Args:
            text: Text to embed
            
        Returns:
            List containing dictionaries with embedding vector and metadata
        """
        logger.info(f"Starting embedding generation for text of length: {len(text)} characters")
        
        try:




            # Check cost limit
 
            # Chunk the text if needed
            chunks = self.text_chunker.chunk_text(text)
            logger.info(f"Text split into {len(chunks)} chunks (size: {self.text_chunker.chunk_size}, overlap: {self.text_chunker.chunk_overlap})")
            
            # Store all embeddings
            all_embeddings = [] 
            start_time = time.time()
            
            # Use batching for better throughput
            # Process chunks in batches instead of one at a time
            batch_size = 10  # Adjust based on your needs
            start_idx = 0
            
            while start_idx < len(chunks):
                batch_chunks = chunks[start_idx:start_idx+batch_size]
                try: 
                    # Process batch results
                    for j, chunk_text in enumerate(batch_chunks):
                        chunk_idx = start_idx + j
                        if chunk_idx < len(chunks):
                            try:
                                # BGE-M3 expects a list of strings, even for a single document
                                # Make sure we're passing a list with a single string instead of just the string
                                embeddings = embedding_fn.encode_documents([chunk_text])
                            except Exception as e:
                                import traceback
                                logger.error(traceback.format_exc())
                                
                                logger.error(f"Error generating embeddings for chunk {chunk_idx}: {str(e)}")
                                continue
                        
                            all_embeddings.append({
                                "chunk_index": chunk_idx,
                                DENSE_EMBEDDING_NAME: embeddings["dense"], 
                                SPARSE_FLOAT_VECTOR_NAME: embeddings["sparse"],
                                "content": chunks[chunk_idx],
                                "content_preview": chunks[chunk_idx][:100] + "..." if len(chunks[chunk_idx]) > 100 else chunks[chunk_idx]
                            }) 

                    logger.debug(f"Generated embeddings for chunks {start_idx+1}-{start_idx+len(batch_chunks)}/{len(chunks)}")
                except Exception as batch_error:
                    logger.error(f"Error generating embeddings for batch starting at {start_idx}: {str(batch_error)}")
                
                start_idx += batch_size
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            
 
            # Return results
            result = {
                "embeddings": all_embeddings,
                "chunk_count": len(chunks), 
                "extra_data": {
                    "model": "BAAI/bge-m3",
                    "chunks": len(chunks),
                    "chunk_size": self.text_chunker.chunk_size,
                    "chunk_overlap": self.text_chunker.chunk_overlap, 
                    "elapsed_time": elapsed_time
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise e


embeddingService = EmbeddingServiceMilvus()