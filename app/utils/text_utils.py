#!/usr/bin/env python3
"""
Text utility functions for the Mail Analysis API.
"""

import re
from typing import Optional
from loguru import logger

try:
    import html2text
    html2text_available = True
except ImportError:
    html2text_available = False
    logger.warning("html2text library not available, using fallback HTML to Markdown conversion")

def html_to_markdown(html_content: str) -> str:
    """
    Convert HTML content to Markdown format.
    
    Args:
        html_content: HTML content to convert
        
    Returns:
        Markdown formatted text
    """
    if not html_content:
        return ""
    
    try:
        if html2text_available:
            # Use html2text library for conversion
            converter = html2text.HTML2Text()
            converter.ignore_links = False
            converter.ignore_images = False
            converter.ignore_tables = False
            converter.body_width = 0  # Don't wrap text
            return converter.handle(html_content)
        else:
            # Fallback simple HTML to Markdown conversion
            markdown = html_content
            
            # Remove HTML doctype and meta tags
            markdown = re.sub(r'<!DOCTYPE.*?>', '', markdown, flags=re.DOTALL)
            markdown = re.sub(r'<head>.*?</head>', '', markdown, flags=re.DOTALL)
            
            # Convert common HTML elements to Markdown
            # Headers
            markdown = re.sub(r'<h1>(.*?)</h1>', r'# \1', markdown)
            markdown = re.sub(r'<h2>(.*?)</h2>', r'## \1', markdown)
            markdown = re.sub(r'<h3>(.*?)</h3>', r'### \1', markdown)
            
            # Lists
            markdown = re.sub(r'<ul>(.*?)</ul>', r'\1', markdown, flags=re.DOTALL)
            markdown = re.sub(r'<li>(.*?)</li>', r'- \1\n', markdown)
            
            # Links
            markdown = re.sub(r'<a href="(.*?)">(.*?)</a>', r'[\2](\1)', markdown)
            
            # Bold and Italic
            markdown = re.sub(r'<strong>(.*?)</strong>', r'**\1**', markdown)
            markdown = re.sub(r'<b>(.*?)</b>', r'**\1**', markdown)
            markdown = re.sub(r'<em>(.*?)</em>', r'*\1*', markdown)
            markdown = re.sub(r'<i>(.*?)</i>', r'*\1*', markdown)
            
            # Paragraphs and line breaks
            markdown = re.sub(r'<p>(.*?)</p>', r'\1\n\n', markdown, flags=re.DOTALL)
            markdown = re.sub(r'<br\s*/?>', r'\n', markdown)
            
            # Tables - simplified conversion (without alignment)
            markdown = re.sub(r'<table>(.*?)</table>', r'\1', markdown, flags=re.DOTALL)
            markdown = re.sub(r'<tr>(.*?)</tr>', r'\1\n', markdown, flags=re.DOTALL)
            markdown = re.sub(r'<th>(.*?)</th>', r'| \1 ', markdown)
            markdown = re.sub(r'<td>(.*?)</td>', r'| \1 ', markdown)
            
            # Remove any remaining HTML tags
            markdown = re.sub(r'<.*?>', '', markdown)
            
            # Normalize newlines and whitespace
            markdown = re.sub(r'\n{3,}', r'\n\n', markdown)
            markdown = markdown.strip()
            
            return markdown
            
    except Exception as e:
        logger.error(f"Error converting HTML to Markdown: {str(e)}")
        # Return raw HTML if conversion fails
        return html_content

def clean_text(text: str, remove_urls: bool = False, remove_emails: bool = False) -> str:
    """
    Clean text by removing unwanted elements.
    
    Args:
        text: Text to clean
        remove_urls: Flag to remove URLs
        remove_emails: Flag to remove email addresses
        
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Remove URLs if requested
    if remove_urls:
        text = re.sub(r'https?://\S+', '', text)
        
    # Remove email addresses if requested
    if remove_emails:
        text = re.sub(r'\S+@\S+\.\S+', '', text)
    
    # Remove multiple newlines
    text = re.sub(r'\n{3,}', r'\n\n', text)
    
    # Remove extra whitespace
    text = re.sub(r'\s{2,}', ' ', text)
    
    return text.strip()
