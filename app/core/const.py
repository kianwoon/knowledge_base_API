#!/usr/bin/env python3
"""
Constants module for the Mail Analysis API.
"""

from enum import Enum


class JobType(Enum):
    """Defines job types for worker processing."""
    
    SUBJECT_ANALYSIS = "analysis"
    MAIL_ANALYSIS = "mail_analysis"
    EMBEDDING = "text_embedding"