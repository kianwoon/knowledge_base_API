import time
from typing import Any, Dict, List

from loguru import logger

from app.utils.text_chunker import TextChunker
from fastembed import  TextEmbedding, LateInteractionTextEmbedding, SparseTextEmbedding 
from FlagEmbedding import BGEM3FlagModel

from app.core.const import DENSE_EMBEDDING_NAME, BM25_EMBEDDING_NAME, LATE_INTERACTION_EMBEDDING_NAME

dense_embedding_model =  TextEmbedding("BAAI/bge-base-en-v1.5") 
bm25_embedding_model = SparseTextEmbedding("Qdrant/bm25")
late_interaction_embedding_model = LateInteractionTextEmbedding("colbert-ir/colbertv2.0")


class EmbeddingService():
    """Service for interacting with OpenAI API."""
    
    def __init__(self,   text_chunker: TextChunker = None):   
        """Initialize OpenAI service.
        
        Args:
            key_manager: Key manager for API keys
            cost_tracker: Cost tracker for API usage
            text_chunker: Text chunker for splitting text into manageable pieces
        """
 
        self.text_chunker = text_chunker or TextChunker()
        
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
            # if not await self.cost_tracker.check_limit():
            #     logger.warning("OpenAI API monthly cost limit reached")
            #     raise Exception("OpenAI API monthly cost limit reached")

            # 

            # dense_embedding_model = BGEM3FlagModel('BAAI/bge-m3',  
            #            use_fp16=False)


            # output_1 = model.encode(sentences_1, return_dense=True, return_sparse=True, return_colbert_vecs=False)
            # output_2 = model.encode(sentences_2, return_dense=True, return_sparse=True, return_colbert_vecs=False)


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
                    for j, embedding_data in enumerate(batch_chunks):
                        chunk_idx = start_idx + j
                        if chunk_idx < len(chunks):

                            # dense_embedding = dense_embedding_model.encode(embedding_data, return_dense=True, return_sparse=True, return_colbert_vecs=True)

                            dense_embedding = list(dense_embedding_model.embed(embedding_data))
                            bm25_embeddings = list(bm25_embedding_model.embed(embedding_data))
                            late_interaction_embeddings = list(late_interaction_embedding_model.embed(embedding_data))

                            all_embeddings.append({
                                "chunk_index": chunk_idx,
                                DENSE_EMBEDDING_NAME: dense_embedding,
                                BM25_EMBEDDING_NAME: bm25_embeddings,
                                LATE_INTERACTION_EMBEDDING_NAME: late_interaction_embeddings,
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
                "_metadata": {
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


embeddingService = EmbeddingService()