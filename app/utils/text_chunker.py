#!/usr/bin/env python3
"""
Text chunking utility for breaking long texts into smaller chunks.
"""

from typing import List, Optional
import os
from loguru import logger

class TextChunker:
    """Utility for chunking text into smaller pieces with overlap."""
    
    def __init__(self, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None):
        """
        Initialize the text chunker.
        
        Args:
            chunk_size: Size of each chunk (in characters)
            chunk_overlap: Overlap between chunks (in characters)
        """
        # Get default values from environment variables or use provided values
        self.chunk_size = chunk_size or int(os.environ.get("CHUNK_SIZE", 300))
        self.chunk_overlap = chunk_overlap or int(os.environ.get("CHUNK_OVERLAP", 50))
        
        # Validate parameters
        if self.chunk_size <= 0:
            logger.warning(f"Invalid chunk size: {self.chunk_size}, using default of 300")
            self.chunk_size = 300
            
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            logger.warning(f"Invalid chunk overlap: {self.chunk_overlap}, using default of 50")
            self.chunk_overlap = 50
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks with specified size and overlap.
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
            
        # If text is smaller than chunk size, return as is
        if len(text) <= self.chunk_size:
            return [text]
            
        chunks = []
        start = 0
        
        while start < len(text):
            # Get end position for current chunk
            end = start + self.chunk_size
            
            # If we're at the end of the text, just add the last chunk
            if end >= len(text):
                chunks.append(text[start:])
                break
                
            # Try to find a good breaking point (newline or period) near the end
            # to avoid cutting sentences in the middle
            break_point = self._find_break_point(text, end)
            
            # Add the chunk using the determined break point
            chunks.append(text[start:break_point])
            
            # Move start position for next chunk, considering overlap
            start = break_point - self.chunk_overlap
            if start < 0:
                start = 0
        
        return chunks
    
    def _find_break_point(self, text: str, position: int) -> int:
        """
        Find a good breaking point near the given position.
        Prefers sentence or paragraph breaks.
        
        Args:
            text: Text to search in
            position: Target position
            
        Returns:
            Position of a suitable break point
        """
        # Look for paragraph break in a window around the position
        window_size = 50  # Characters to search back
        search_start = max(0, position - window_size)
        search_text = text[search_start:position]
        
        # Try to find paragraph break (double newline)
        paragraph_break = search_text.rfind("\n\n")
        if paragraph_break != -1:
            return search_start + paragraph_break + 2  # +2 to skip the newlines
        
        # Try to find single newline
        newline = search_text.rfind("\n")
        if newline != -1:
            return search_start + newline + 1  # +1 to skip the newline
        
        # Try to find sentence end (period followed by space)
        sentence_end = search_text.rfind(". ")
        if sentence_end != -1:
            return search_start + sentence_end + 2  # +2 to skip the period and space
        
        # If no good break found, just use the position
        return position
