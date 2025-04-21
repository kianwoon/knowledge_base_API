"""
Constants module for the Mail Analysis API.
"""

from enum import Enum


class JobType(Enum):
    """Defines job types for worker processing."""
    
    SUBJECT_ANALYSIS = "analysis"
    MAIL_ANALYSIS = "mail_analysis"
    EMBEDDING = "text_embedding"



# Define constants for embedding names
DENSE_EMBEDDING_NAME = "dense_embedding"
BM25_EMBEDDING_NAME = "bm25_embedding"
LATE_INTERACTION_EMBEDDING_NAME = "late_interaction_embedding"
SPARSE_FLOAT_VECTOR_NAME = "sparse_float_vector"