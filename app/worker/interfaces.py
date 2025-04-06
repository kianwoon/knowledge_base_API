#!/usr/bin/env python3
"""
Interfaces for the Worker module following SOLID principles.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class JobProcessor(ABC):
    """
    Interface for job processors that handle different types of jobs.
    Following the Interface Segregation Principle.
    """
    
    @abstractmethod
    async def process(self, job_data: Dict[str, Any], job_id: str, trace_id: str) -> Dict[str, Any]:
        """
        Process a job and return results.
        
        Args:
            job_data: Job data
            job_id: Job ID
            trace_id: Trace ID
            
        Returns:
            Processing results
        """
        pass


class JobRepository(ABC):
    """
    Interface for job data storage operations.
    Following the Dependency Inversion Principle.
    """
    @abstractmethod
    async def connect_with_retry(self) -> None:
        """
        Connect to the job repository with retry logic.
        """
        pass

    @abstractmethod
    async def ping(self) -> None:
        """
        Ping the job repository to check connectivity.
        """
        pass

    @abstractmethod
    async def get_job_id(self, job_key: str) -> Optional[str]:
        """
        Get job ID by job key.
        
        Args:
            job_key: Job key
            
        Returns:
            Job ID or None if not found
        """
        pass
    
    @abstractmethod
    async def get_job_data(self, job_id: str) -> Optional[str]:
        """
        Get job data.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job data as JSON string or None if not found
        """
        pass
    
    @abstractmethod
    async def get_job_type(self, job_id: str) -> Optional[str]:
        """
        Get job type.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job type or None if not found
        """
        pass
    
    @abstractmethod
    async def store_job_results(self, job_id: str, results: Dict[str, Any], expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Store job results.
        
        Args:
            job_id: Job ID
            results: Job results
            expiration: Expiration time in seconds (default: 7 days)
        """
        pass
    
    @abstractmethod
    async def update_job_status(self, job_id: str, status: str, expiration: int = 60 * 60 * 24 * 7) -> None:
        """
        Update job status.
        
        Args:
            job_id: Job ID
            status: Job status
            expiration: Expiration time in seconds (default: 7 days)
        """
        pass
    
    @abstractmethod
    async def store_job_error(self, job_id: str, error: str, expiration: int = 60 * 60 * 24) -> None:
        """
        Store job error.
        
        Args:
            job_id: Job ID
            error: Error message
            expiration: Expiration time in seconds (default: 24 hours)
        """
        pass
    
    @abstractmethod
    async def get_pending_jobs(self) -> list:
        """
        Get pending jobs.
        
        Returns:
            List of pending job keys
        """
        pass
    
    @abstractmethod
    async def get_job_status(self, job_key: str) -> Optional[str]:
        """
        Get job status.
        
        Args:
            job_key: Job key
            
        Returns:
            Job status or None if not found
        """
        pass


class Notifier(ABC):
    """
    Base interface for all notification types.
    Following the Single Responsibility Principle.
    """
    
    @abstractmethod
    async def send_notification(self, data: Dict[str, Any], job_id: str, trace_id: str) -> None:
        """
        Send notification with job results.
        
        Args:
            data: Data to send in the notification
            job_id: Job ID
            trace_id: Trace ID
        """
        pass


class NotifierFactory(ABC):
    """
    Interface for notifier factory.
    Following the Factory Method Pattern.
    """
    
    @abstractmethod
    def get_notifier(self, notifier_type: str) -> Notifier:
        """
        Get notifier for the given notification type.
        
        Args:
            notifier_type: Notification type (e.g., 'webhook', 'email', 'sms')
            
        Returns:
            Appropriate notifier implementation
        """
        pass


class JobFactory(ABC):
    """
    Interface for job processor factory.
    Following the Factory Method Pattern.
    """
    
    @abstractmethod
    def get_processor(self, job_type: str) -> JobProcessor:
        """
        Get job processor for the given job type.
        
        Args:
            job_type: Job type
            
        Returns:
            Job processor
        """
        pass