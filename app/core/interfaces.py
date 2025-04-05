#!/usr/bin/env python3
"""
Interfaces for the Mail Analysis API.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union


class CacheInterface(ABC):
    """Interface for cache operations."""
    
    @abstractmethod
    async def connect(self) -> None:
        """Connect to the cache."""
        pass
        
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the cache."""
        pass
        
    @abstractmethod
    async def get(self, key: str) -> Any:
        """Get value from cache."""
        pass
        
    @abstractmethod
    async def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        pass
        
    @abstractmethod
    async def setex(self, key: str, seconds: int, value: Any) -> None:
        """Set value in cache with expiration."""
        pass
        
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        pass
        
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass
        
    @abstractmethod
    async def incr(self, key: str) -> int:
        """Increment value in cache."""
        pass
        
    @abstractmethod
    async def incrby(self, key: str, amount: int) -> int:
        """Increment value in cache by amount."""
        pass
        
    @abstractmethod
    async def incrbyfloat(self, key: str, amount: float) -> float:
        """Increment float value in cache by amount."""
        pass
        
    @abstractmethod
    async def ttl(self, key: str) -> int:
        """Get time to live for key."""
        pass
        
    @abstractmethod
    async def expire(self, key: str, seconds: int) -> None:
        """Set expiration time for key."""
        pass


class KeyManagerInterface(ABC):
    """Interface for API key management."""
    
    @abstractmethod
    async def get_api_key(self) -> str:
        """Get an available API key."""
        pass
        
    @abstractmethod
    async def mark_key_limited(self, key: str, duration: int = 60) -> None:
        """Mark an API key as rate limited."""
        pass


class CostTrackerInterface(ABC):
    """Interface for cost tracking."""
    
    @abstractmethod
    def calculate_cost(self, model: str, tokens: int) -> float:
        """Calculate cost for API usage."""
        pass
        
    @abstractmethod
    async def track_usage(self, model: str, tokens: int) -> None:
        """Track API usage."""
        pass
        
    @abstractmethod
    async def check_limit(self) -> bool:
        """Check if monthly cost limit has been reached."""
        pass
        
    @abstractmethod
    async def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        pass


class AIServiceInterface(ABC):
    """Interface for AI service operations."""
    
    @abstractmethod
    async def analyze_text(self, text: str, analysis_type: str) -> Dict[str, Any]:
        """Analyze text using AI."""
        pass
        
    @abstractmethod
    async def analyze_subjects(self, subjects: List[str], min_confidence: float = 0.7, 
                              job_id: str = None, trace_id: str = None) -> Dict[str, Any]:
        """Analyze a list of email subject lines."""
        pass