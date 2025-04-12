"""
Celery module for the Mail Analysis API.
This module exports the Celery instance for use throughout the application.
"""

# Export the celery app directly from the worker module
from app.celery.worker import celery

__all__ = ['celery']