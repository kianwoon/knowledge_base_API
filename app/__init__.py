"""
Mail Analysis API package.
"""

__version__ = "0.1.0"

# Import Celery instance from the celery package
from app.celery import celery

__all__ = ['celery']
