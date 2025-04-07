#!/usr/bin/env python3
"""
Text utility functions for the Mail Analysis API.
"""

import re
from typing import Optional
from loguru import logger
import json
import io
from typing import Dict, List, Any

# Try importing pandas, which is the best library for Excel handling
try:
    import pandas as pd
    pandas_available = True
except ImportError:
    pandas_available = False
    logger.warning("pandas library not available, Excel conversion will be limited")

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

def convert_excel_to_json(content: str) -> str:
    """
    Convert Excel content to JSON format.
    
    Args:
        content: Excel file content as string or bytes
        
    Returns:
        JSON string representation of the Excel data
    """
    if not content:
        return ""
    
    try:
        # If content is already in text form, just return it
        if isinstance(content, str) and (content.startswith("{") or content.startswith("[")):
            return content
            
        if pandas_available:
            # Convert content to bytes if it's a string
            if isinstance(content, str):
                try:
                    # Try to decode as base64
                    import base64
                    binary_content = base64.b64decode(content)
                except:
                    # If not base64, encode as UTF-8
                    binary_content = content.encode('utf-8')
            else:
                binary_content = content
            
            # Create BytesIO object for pandas to read
            excel_file = io.BytesIO(binary_content)
            
            # Read all sheets from the Excel file
            result = {}
            excel_data = pd.read_excel(excel_file, sheet_name=None)
            
            # Convert each sheet to JSON
            for sheet_name, df in excel_data.items():
                # Convert datetime columns to strings
                for col in df.select_dtypes(include=['datetime64']).columns:
                    df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
                
                # Replace NaN values with None for proper JSON serialization
                df = df.where(pd.notna(df), None)
                
                # Convert to list of dictionaries (records)
                sheet_data = df.to_dict(orient='records')
                
                # Process any remaining Timestamp objects
                processed_data = []
                for record in sheet_data:
                    processed_record = {}
                    for key, value in record.items():
                        # Convert any pandas Timestamp objects to strings
                        if hasattr(value, 'strftime'):
                            processed_record[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            processed_record[key] = value
                    processed_data.append(processed_record)
                    
                result[sheet_name] = processed_data
            
            # Custom JSON encoder for any other date/time types
            class CustomJSONEncoder(json.JSONEncoder):
                def default(self, obj):
                    if hasattr(obj, 'strftime'):
                        return obj.strftime('%Y-%m-%d %H:%M:%S')
                    return super().default(obj)
            
            # Convert the final result to JSON using the custom encoder
            return json.dumps(result, ensure_ascii=False, cls=CustomJSONEncoder)
        else:
            # Fallback for when pandas isn't available
            logger.warning("pandas not available for Excel conversion, returning simple text")
            
            # If content is bytes, try to decode it
            if not isinstance(content, str):
                try:
                    return content.decode('utf-8')
                except:
                    return "Excel content couldn't be converted without pandas library."
            return content
    except Exception as e:
        logger.error(f"Error converting Excel to JSON: {str(e)}")
        # Return a simplified error message in JSON format
        return json.dumps({
            "error": f"Failed to convert Excel file: {str(e)}",
            "text": content[:1000] + "..." if len(content) > 1000 else content
        })

def convert_to_text(content: str, file_type: str) -> str:
    """
    Convert attachment content to plain text based on file type.
    
    Args:
        content: The content or text representation of the file
        file_type: The MIME type or file extension of the attachment
        
    Returns:
        Extracted text from the attachment
    """
    # If content is already provided as text, just return it
    if not content:
        return ""
    
    # Normalize file type to lowercase
    file_type = file_type.lower().strip()
    
    try:
        # Handle different file types based on MIME types or extensions
        # PDF files
        if "application/pdf" in file_type or file_type.endswith(".pdf"):
            # For PDF content that might be pre-extracted
            return "" # Placeholder for PDF extraction logic
            
        # Word documents - use exact matching for MIME types and extension checking for simple types
        elif (file_type == "application/msword" or 
              file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or
              file_type.endswith(".docx") or file_type.endswith(".doc") or 
              file_type == "word"):
            # For Word document content that might be pre-extracted
            return "" # Placeholder for PDF extraction logic
            
        # Excel files - use exact matching for MIME types and extension checking for simple types
        elif (file_type == "application/vnd.ms-excel" or
              file_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" or
              file_type.endswith(".xlsx") or file_type.endswith(".xls") or
              file_type == "excel"):
            # For Excel content that might be pre-extracted
            return convert_excel_to_json(content)
            
        # Text files
        elif any(x in file_type for x in ["text/plain", "text/csv", "text/markdown", "text/tab-separated-values",
                                         "text/", "txt", "csv", "md", "tsv"]):
            # Plain text, return as is
            return "" # Placeholder for PDF extraction logic
            
        # PowerPoint files
        elif any(x in file_type for x in ["application/vnd.ms-powerpoint", 
                                         "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                         "powerpoint", "ppt", "pptx"]):
            # For PowerPoint content that might be pre-extracted
            return "" # Placeholder for PDF extraction logic
            
        # HTML content
        elif "text/html" in file_type or "html" in file_type:
            # Convert HTML to markdown for better text representation
            return html_to_markdown(content)
            
        # Default case - return content as is
        else:
            # Default case - return content as is
            return "" # Placeholder for PDF extraction logic
    
    except Exception as e:
        from loguru import logger
        logger.error(f"Error extracting text from {file_type} attachment: {str(e)}")
        # Return whatever content we have
        return "" # Placeholder for PDF extraction logic
