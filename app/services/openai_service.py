#!/usr/bin/env python3
"""
AI service module for the Mail Analysis API.
"""

import os
import re
import time
import json
from typing import Dict, List, Any
from openai import AsyncOpenAI
from loguru import logger

from app.core.config import config
from app.core.interfaces import KeyManagerInterface, CostTrackerInterface, AIServiceInterface, CacheInterface
from app.core.redis import redis_client
from app.utils.text_chunker import TextChunker


class OpenAIKeyManager(KeyManagerInterface):
    """Manager for OpenAI API keys."""
    
    def __init__(self, cache: CacheInterface = None):
        """Initialize OpenAI key manager.
        
        Args:
            cache: Cache interface for storing key status
        """
        self.cache = cache or redis_client
        self.primary_key = config.get("openai", {}).get("api_key")
        self.backup_keys = config.get("openai", {}).get("backup_api_keys", "").split(",")
        
        # Use environment variable if available
        if os.environ.get("OPENAI_API_KEY"):
            self.primary_key = os.environ.get("OPENAI_API_KEY")
            
        if os.environ.get("OPENAI_BACKUP_API_KEYS"):
            self.backup_keys = os.environ.get("OPENAI_BACKUP_API_KEYS").split(",")
        
    async def get_api_key(self) -> str:
        """Get an available API key.
        
        Returns:
            OpenAI API key
        
        Raises:
            Exception: If no API keys are available
        """
        try:
            #return self.primary_key
            # Check if primary key is rate limited
            primary_limited = await self.cache.get("openai_limited:primary")
            
            if not primary_limited and self.primary_key:
                return self.primary_key
                
            # Try backup keys
            for i, key in enumerate(self.backup_keys):
                if key and not await self.cache.get(f"openai_limited:backup_{i}"):
                    return key
                    
            # All keys are rate limited
            raise Exception("All OpenAI API keys are currently rate limited")
        except Exception as e:
            logger.error(f"Error getting API key: {str(e)}")
            # If cache fails, return primary key as fallback
            if self.primary_key:
                return self.primary_key
            elif self.backup_keys and self.backup_keys[0]:
                return self.backup_keys[0]
            else:
                raise Exception("No AI API keys available and cache connection failed")
        
    async def mark_key_limited(self, key: str, duration: int = 60) -> None:
        """Mark an API key as rate limited.
        
        Args:
            key: API key
            duration: Duration in seconds to mark as limited
        """
        try:
            if key == self.primary_key:
                await self.cache.setex("openai_limited:primary", duration, "1")
                logger.warning("Primary OpenAI API key rate limited")
            else:
                for i, backup_key in enumerate(self.backup_keys):
                    if key == backup_key:
                        await self.cache.setex(f"openai_limited:backup_{i}", duration, "1")
                        logger.warning(f"Backup OpenAI API key {i} rate limited")
                        break
        except Exception as e:
            logger.error(f"Error marking key as limited: {str(e)}")
            # Continue execution even if cache operation fails


class OpenAICostTracker(CostTrackerInterface):
    """Tracker for OpenAI API costs."""
    
    def __init__(self, cache: CacheInterface = None):
        """Initialize OpenAI cost tracker.
        
        Args:
            cache: Cache interface for storing usage data
        """
        self.cache = cache or redis_client
        self.model_costs = {
            "gpt-4": 0.03,  # $0.03 per 1K tokens
            "gpt-4o": 0.01,  # $0.01 per 1K tokens
            "gpt-4o-mini": 0.00015,  # $0.00015 per 1K tokens ($0.15 per 1M tokens)
        }
        
    def calculate_cost(self, model: str, tokens: int) -> float:
        """Calculate cost for API usage.
        
        Args:
            model: Model name
            tokens: Number of tokens
            
        Returns:
            Cost in USD
        """
        # Get cost per 1K tokens for model
        cost_per_1k = self.model_costs.get(model, 0.01)  # Default to $0.01 per 1K tokens
        
        # Calculate cost
        return (tokens / 1000) * cost_per_1k
        
    async def track_usage(self, model: str, tokens: int) -> None:
        """Track API usage.
        
        Args:
            model: Model name
            tokens: Number of tokens
        """
        try:
            # Calculate cost
            cost = self.calculate_cost(model, tokens)
            
            # Track monthly cost
            await self.cache.incrby("openai:monthly_tokens", tokens)
            await self.cache.incrbyfloat("openai:monthly_cost", cost)
            
            # Set expiry if not already set (31 days)
            if not await self.cache.ttl("openai:monthly_cost"):
                await self.cache.expire("openai:monthly_cost", 31 * 24 * 60 * 60)
                await self.cache.expire("openai:monthly_tokens", 31 * 24 * 60 * 60)
            
            # Log usage
            logger.info(f"OpenAI API usage: {model}, {tokens} tokens, ${cost:.4f}")
        except Exception as e:
            logger.error(f"Error tracking usage: {str(e)}")
            # Continue execution even if cache operation fails
        
    async def check_limit(self) -> bool:
        """Check if monthly cost limit has been reached.
        
        Returns:
            True if within limit, False otherwise
        """
        try:
            # Get monthly cost limit
            monthly_limit = config.get("openai", {}).get("monthly_cost_limit", 1000)
            
            # Get current monthly cost
            current_cost = float(await self.cache.get("openai:monthly_cost") or 0)
            
            # Check if limit reached
            if current_cost >= monthly_limit:
                logger.warning(f"OpenAI API monthly cost limit reached: ${current_cost:.2f}/{monthly_limit:.2f}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error checking cost limit: {str(e)}")
            return True  # Default to allowing API calls if cache check fails
        
    async def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics.
        
        Returns:
            Dictionary with usage statistics
        """
        try:
            # Get monthly cost limit
            monthly_limit = config.get("openai", {}).get("monthly_cost_limit", 1000)
            
            # Get current usage
            current_cost = float(await self.cache.get("openai:monthly_cost") or 0)
            current_tokens = int(await self.cache.get("openai:monthly_tokens") or 0)
            
            # Calculate percentage of limit
            percentage = (current_cost / monthly_limit) * 100 if monthly_limit > 0 else 0
            
            return {
                "monthly_cost": current_cost,
                "monthly_tokens": current_tokens,
                "monthly_limit": monthly_limit,
                "percentage": percentage,
                "remaining": monthly_limit - current_cost
            }
        except Exception as e:
            logger.error(f"Error getting usage stats: {str(e)}")
            # Return default values if cache operation fails
            return {
                "monthly_cost": 0,
                "monthly_tokens": 0,
                "monthly_limit": config.get("openai", {}).get("monthly_cost_limit", 1000),
                "percentage": 0,
                "remaining": config.get("openai", {}).get("monthly_cost_limit", 1000)
            }


def sanitize_prompt(prompt: str) -> str:
    """Sanitize prompt to prevent prompt injection.
    
    Args:
        prompt: User-provided prompt
        
    Returns:
        Sanitized prompt
    """
    # Remove potential system instruction overrides
    sanitized = re.sub(r"(^|\n)system:", "", prompt)
    
    # Remove potential role changes
    sanitized = re.sub(r"(^|\n)(user|assistant|system):", "", sanitized)
    
    # Remove markdown code block syntax that might be used to hide instructions
    sanitized = re.sub(r"```.*?```", "", sanitized, flags=re.DOTALL)
    
    return sanitized


class OpenAIService(AIServiceInterface):
    """Service for interacting with OpenAI API."""
    
    def __init__(self, key_manager: KeyManagerInterface = None, cost_tracker: CostTrackerInterface = None):
        """Initialize OpenAI service.
        
        Args:
            key_manager: Key manager for API keys
            cost_tracker: Cost tracker for API usage
        """
        self.key_manager = key_manager or OpenAIKeyManager()
        self.cost_tracker = cost_tracker or OpenAICostTracker()
        self.text_chunker = TextChunker()
        
    async def embeding_text(self, text: str) -> Dict[str, Any]:
        """Get embedding for text using OpenAI API.
        
        Args:
            text: Text to embed
            
        Returns:
            Dictionary containing embedding vector and metadata
        """
        logger.info(f"Starting embedding generation for text of length: {len(text)} characters")
        
        try:
            # Check cost limit
            if not await self.cost_tracker.check_limit():
                logger.warning("OpenAI API monthly cost limit reached")
                raise Exception("OpenAI API monthly cost limit reached")
                
            # Get API key
            api_key = await self.key_manager.get_api_key()
            logger.debug("Successfully retrieved API key")
            
            # Initialize OpenAI client with API key
            client = AsyncOpenAI(api_key=api_key)
            logger.debug("Initialized AsyncOpenAI client") 
            embedding_model = config.get("openai", {}).get("embedding_model", "text-embedding-3-small")

            logger.info(f"Using embedding model: {embedding_model}")
            
            # Chunk the text if needed
            chunks = self.text_chunker.chunk_text(text)
            logger.info(f"Text split into {len(chunks)} chunks (size: {self.text_chunker.chunk_size}, overlap: {self.text_chunker.chunk_overlap})")
            
            # Store all embeddings
            all_embeddings = []
            total_tokens = 0
            start_time = time.time()
            
            # Use batching for better throughput
            # Process chunks in batches instead of one at a time
            batch_size = 10  # Adjust based on your needs
            start_idx = 0
            
            while start_idx < len(chunks):
                batch_chunks = chunks[start_idx:start_idx+batch_size]
                try:
                    batch_response = await client.embeddings.create(
                        model=embedding_model,
                        input=batch_chunks
                    )
                    
                    # Process batch results
                    for j, embedding_data in enumerate(batch_response.data):
                        chunk_idx = start_idx + j
                        if chunk_idx < len(chunks):
                            all_embeddings.append({
                                "chunk_index": chunk_idx,
                                "embedding": embedding_data.embedding,
                                # Include more contextual info for better RAG retrieval
                                "content": chunks[chunk_idx],
                                "content_preview": chunks[chunk_idx][:100] + "..." if len(chunks[chunk_idx]) > 100 else chunks[chunk_idx]
                            })
                    
                    # Track tokens
                    batch_tokens = batch_response.usage.total_tokens
                    total_tokens += batch_tokens
                    
                    logger.debug(f"Generated embeddings for chunks {start_idx+1}-{start_idx+len(batch_chunks)}/{len(chunks)}")
                except Exception as batch_error:
                    logger.error(f"Error generating embeddings for batch starting at {start_idx}: {str(batch_error)}")
                
                start_idx += batch_size
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            
            # Track usage
            try:
                await self.cost_tracker.track_usage(
                    embedding_model,
                    total_tokens
                )
            except Exception as e:
                logger.warning(f"Failed to track embedding usage: {str(e)}")
            
            # Return results
            result = {
                "embeddings": all_embeddings,
                "chunk_count": len(chunks),
                "model": embedding_model,
                "_metadata": {
                    "model": embedding_model,
                    "chunks": len(chunks),
                    "chunk_size": self.text_chunker.chunk_size,
                    "chunk_overlap": self.text_chunker.chunk_overlap,
                    "total_tokens": total_tokens,
                    "elapsed_time": elapsed_time
                }
            }
            
            return result
            
        except Exception as e:
            # Check if it's a rate limit error based on error message
            error_message = str(e).lower()
            if "rate limit" in error_message:
                # Mark key as rate limited
                await self.key_manager.mark_key_limited(api_key)
                
                # Try again with a different key
                return await self.embeding_text(text)
            else:
                # For other types of errors
                logger.error(f"Error generating embedding: {str(e)}")
                raise

    async def analyze_text(self, text: str, analysis_type: str) -> Dict[str, Any]:
        """Analyze text using OpenAI API.
        
        Args:
            text: Text to analyze
            analysis_type: Type of analysis to perform
            
        Returns:
            Analysis results
        """
        logger.info(f"Starting analysis of text with type: {analysis_type}")
        logger.debug(f"Text length: {len(text)} characters")
        
        try:
            # Check cost limit
            if not await self.cost_tracker.check_limit():
                logger.warning("OpenAI API monthly cost limit reached")
                raise Exception("OpenAI API monthly cost limit reached")
                
            # Get API key
            api_key = await self.key_manager.get_api_key()
            logger.debug("Successfully retrieved API key")
            
            # Initialize OpenAI client with API key
            client = AsyncOpenAI(api_key=api_key)
            logger.debug("Initialized AsyncOpenAI client")
            
            # Get model
            model_choices = config.get("openai", {}).get("model_choices", ["gpt-4o-mini"])
            model = model_choices[0]  # Use first model in list
            logger.info(f"Using model: {model}")
            
            # Get max tokens
            max_tokens = config.get("openai", {}).get("max_tokens_per_request", 40960)
            logger.debug(f"Max tokens set to: {max_tokens}")
            
            # Prepare prompt based on analysis type
            system_prompt = self._get_system_prompt(analysis_type)
            logger.debug(f"System prompt length: {len(system_prompt)} characters")
            
            # Sanitize user text
            sanitized_text = sanitize_prompt(text)
            logger.debug(f"Sanitized text length: {len(sanitized_text)} characters")
            
            # Call OpenAI API
            logger.info(f"Calling OpenAI API with model {model} for {analysis_type}, system: {system_prompt}, user: {sanitized_text}")   
            start_time = time.time()
            
            try:                     
                
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": sanitized_text}
                    ],
                    max_tokens=max_tokens,
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                logger.info(f"OpenAI API call successful for {analysis_type}")
            except Exception as api_error:
                logger.error(f"OpenAI API call failed: {str(api_error)}")
                raise
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            
            # Track usage
            try:
                await self.cost_tracker.track_usage(
                    model,
                    response.usage.total_tokens
                )
            except Exception as e:
                logger.warning(f"Failed to track usage: {str(e)}")
            
            # Parse response
            try:
                result = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError:
                # Fallback to raw text if not valid JSON
                result = {"raw_response": response.choices[0].message.content}
                
            # Add metadata
            result["_metadata"] = {
                "model": model,
                "tokens": response.usage.total_tokens,
                "elapsed_time": elapsed_time
            }
            
            return result
            
        except Exception as e:
            # Check if it's a rate limit error based on error message
            error_message = str(e).lower()
            if "rate limit" in error_message:
                # Mark key as rate limited
                await self.key_manager.mark_key_limited(api_key)
                
                # Try again with a different key
                return await self.analyze_text(text, analysis_type)
            elif "api" in error_message and "error" in error_message:
                logger.error(f"OpenAI API error: {str(e)}")
                raise
            else:
                # For other types of errors
                logger.error(f"Error analyzing text: {str(e)}")
                raise
            
    async def analyze_subjects(self, subjects: List[str], min_confidence: float = 0.7, 
                              job_id: str = None, trace_id: str = None) -> Dict[str, Any]:
        """Analyze a list of email subject lines.
        
        Args:
            subjects: List of email subject lines
            min_confidence: Minimum confidence threshold for analysis
            job_id: Job ID (optional)
            trace_id: Trace ID (optional)
            
        Returns:
            Analysis results for each subject
        """
        logger.info(f"Starting analysis of {len(subjects)} email subjects, job_id: {job_id}, trace_id: {trace_id}")
        subjects = subjects[:100]  # Todo Limit to 100 subjects
        
        try:
            # Check cost limit
            if not await self.cost_tracker.check_limit():
                logger.warning("OpenAI API monthly cost limit reached")
                raise Exception("OpenAI API monthly cost limit reached")
                
            # Get API key
            api_key = await self.key_manager.get_api_key()
            logger.debug("Successfully retrieved API key")
            
            # Initialize OpenAI client with API key
            client = AsyncOpenAI(api_key=api_key)
            logger.debug("Initialized AsyncOpenAI client")
            
            # Get model
            model_choices = config.get("openai", {}).get("model_choices", ["gpt-4o-mini"])
            model = model_choices[0]  # Use first model in list
            logger.info(f"Using model: {model}")
            
            # Get max tokens
            max_tokens = config.get("openai", {}).get("max_tokens_per_request", 8000)
            logger.debug(f"Max tokens set to: {max_tokens}")
            
            # Prepare prompt for subject analysis
            system_prompt = self._get_system_prompt("subject_analysis")
            
            # Format the subjects as a list in the prompt
            subjects_text = "\n".join([f"- \"{subject}\"" for subject in subjects])
            
            # Sanitize user text
            sanitized_text = sanitize_prompt(subjects_text)
            logger.debug(f"Sanitized text length: {len(sanitized_text)} characters")

            # Call OpenAI API
            logger.info(f"Calling OpenAI API with model {model} for subject analysis, job {job_id}, trace_id: {trace_id}, system: {system_prompt}, user: {sanitized_text}")         
            
            start_time = time.time()
            
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": sanitized_text}
                    ],
                    max_tokens=max_tokens,
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                logger.info("OpenAI API call successful for subject analysis")
                # Call OpenAI API
                logger.info(f"OpenAI API call response: job {job_id}, trace_id: {trace_id}, response: {response.to_json()}")

            except Exception as api_error:
                logger.error(f"OpenAI API call failed: {str(api_error)}")
                raise
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            
            # Track usage
            try:
                await self.cost_tracker.track_usage(
                    model,
                    response.usage.total_tokens
                )
            except Exception as e:
                logger.warning(f"Failed to track usage: {str(e)}")
            
            # Parse response
            try:
                result = json.loads(response.choices[0].message.content)
                
                # Ensure the response has the expected structure
                if "results" not in result or not isinstance(result["results"], list):
                    logger.warning("Unexpected response format from OpenAI API")
                    result = {"results": []}
                
                # Add job_id to result
                result["job_id"] = job_id
                
                return result
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON response from OpenAI API")
                raise Exception("Invalid response format from OpenAI API")
                
        except Exception as e:
            # Check if it's a rate limit error based on error message
            error_message = str(e).lower()
            if "rate limit" in error_message:
                # Mark key as rate limited
                await self.key_manager.mark_key_limited(api_key)
                
                # Try again with a different key
                return await self.analyze_subjects(subjects, min_confidence, job_id, trace_id)
            else:
                # For other types of errors
                logger.error(f"Error analyzing subjects: {str(e)}")
                raise
    
    def _get_system_prompt(self, analysis_type: str) -> str:
        """Get system prompt for analysis type.
        
        Args:
            analysis_type: Type of analysis to perform
            
        Returns:
            System prompt
        """
        # Get prompts from config
        prompts = config.get("prompts", {})
        
        # Get specific prompt if available, otherwise use default
        prompt = prompts.get(analysis_type)
        if prompt:
            return prompt
            
        # Fall back to default prompt if specific one not found
        default_prompt = prompts.get("default", """
        You are an AI assistant that analyzes text. Your task is to analyze the provided text for {analysis_type}.
        
        Return your analysis as a valid JSON object.
        """)
        
        # Replace placeholder with analysis type
        return default_prompt.replace("{analysis_type}", analysis_type)


# Create default instances
key_manager = OpenAIKeyManager()
cost_tracker = OpenAICostTracker()
openai_service = OpenAIService(key_manager, cost_tracker)