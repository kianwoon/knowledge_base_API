#!/usr/bin/env python3
"""
Text utility functions for the Mail Analysis API.
"""

import re
from typing import Optional, Union
from loguru import logger
import json
import io
from typing import Dict, List, Any
import base64

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

# Try importing PDF libraries
try:
    from PyPDF2 import PdfReader
    pypdf2_available = True
except ImportError:
    pypdf2_available = False
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text
        pdfminer_available = True
    except ImportError:
        pdfminer_available = False
        logger.warning("PDF libraries not available, PDF conversion will be limited")

# Try importing PowerPoint libraries
try:
    from pptx import Presentation
    pptx_available = True
except ImportError:
    pptx_available = False
    logger.warning("python-pptx library not available, PowerPoint conversion will be limited")

# Try importing Word document libraries
try:
    import docx
    docx_available = True
except ImportError:
    docx_available = False
    try:
        # Try an alternative library for older .doc files
        import textract
        textract_available = True
    except ImportError:
        textract_available = False
        logger.warning("Word document processing libraries not available, Word conversion will be limited")

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

def convert_pdf_to_markdown(pdf_content: Union[str, bytes]) -> str:
    """
    Convert PDF content to Markdown text format.
    
    Args:
        pdf_content: PDF file content as bytes or base64 encoded string
        
    Returns:
        Markdown formatted text extracted from the PDF
    """
    if not pdf_content:
        return ""
    
    try:
        # Convert content to bytes if it's a string (likely base64)
        if isinstance(pdf_content, str):
            try:
                import base64
                binary_content = base64.b64decode(pdf_content)
            except:
                # If not base64, encode as UTF-8 (though this is unlikely for PDFs)
                binary_content = pdf_content.encode('utf-8')
        else:
            binary_content = pdf_content
        
        # Create BytesIO object for PDF libraries to read
        from io import BytesIO
        pdf_file = BytesIO(binary_content)
        
        extracted_text = ""
        
        if pypdf2_available:
            # Use PyPDF2 for extraction
            reader = PdfReader(pdf_file)
            
            # Extract text from each page
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                page_text = page.extract_text() or ""
                extracted_text += f"## Page {page_num+1}\n\n{page_text}\n\n"
                
        elif pdfminer_available:
            # Fallback to pdfminer.six if PyPDF2 is not available
            # Reset file pointer
            pdf_file.seek(0)
            raw_text = pdfminer_extract_text(pdf_file)
            
            # Simple formatting - split by double newlines which often indicate page breaks
            pages = raw_text.split("\n\n\n")
            for i, page in enumerate(pages):
                if page.strip():
                    extracted_text += f"## Page {i+1}\n\n{page.strip()}\n\n"
        else:
            return "PDF text extraction failed. Required libraries not installed."
        
        # Clean up the text
        extracted_text = clean_text(extracted_text)
        
        return extracted_text
            
    except Exception as e:
        logger.error(f"Error converting PDF to Markdown: {str(e)}")
        return f"Error extracting text from PDF: {str(e)}"

def convert_ppt_to_markdown(ppt_content: Union[str, bytes]) -> str:
    """
    Convert PowerPoint content to Markdown text format.
    
    Args:
        ppt_content: PowerPoint file content as bytes or base64 encoded string
        
    Returns:
        Markdown formatted text extracted from the PowerPoint
    """
    if not ppt_content:
        return ""
    
    try:
        # Convert content to bytes if it's a string (likely base64)
        if isinstance(ppt_content, str):
            try:
                binary_content = base64.b64decode(ppt_content)
            except:
                # If not base64, encode as UTF-8 (though this is unlikely for PPT)
                binary_content = ppt_content.encode('utf-8')
        else:
            binary_content = ppt_content
        
        # Create BytesIO object for the PowerPoint library to read
        from io import BytesIO
        ppt_file = BytesIO(binary_content)
        
        extracted_text = ""
        
        if pptx_available:
            # Use python-pptx for extraction
            presentation = Presentation(ppt_file)
            
            # Extract text from each slide
            for slide_num, slide in enumerate(presentation.slides):
                slide_text = []
                
                # Extract title if present
                if slide.shapes.title:
                    slide_text.append(f"### {slide.shapes.title.text}")
                
                # Extract text from all shapes in the slide
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        # Skip if this is the title we already added
                        if shape != slide.shapes.title:
                            slide_text.append(shape.text)
                
                # Combine all text from this slide
                if slide_text:
                    extracted_text += f"## Slide {slide_num + 1}\n\n"
                    extracted_text += "\n\n".join(slide_text) + "\n\n"
                else:
                    extracted_text += f"## Slide {slide_num + 1}\n\n*No text content*\n\n"
        else:
            return "PowerPoint text extraction failed. The python-pptx library is not installed."
        
        # Clean up the text
        extracted_text = clean_text(extracted_text)
        
        return extracted_text
            
    except Exception as e:
        logger.error(f"Error converting PowerPoint to Markdown: {str(e)}")
        return f"Error extracting text from PowerPoint: {str(e)}"

def convert_word_to_markdown(word_content: Union[str, bytes]) -> str:
    """
    Convert Word document content to Markdown text format.
    
    Args:
        word_content: Word document file content as bytes or base64 encoded string
        
    Returns:
        Markdown formatted text extracted from the Word document
    """
    if not word_content:
        return ""
    
    try:
        # Convert content to bytes if it's a string (likely base64)
        if isinstance(word_content, str):
            try:
                binary_content = base64.b64decode(word_content)
            except:
                # If not base64, encode as UTF-8 (though this is unlikely for Word docs)
                binary_content = word_content.encode('utf-8')
        else:
            binary_content = word_content
        
        # Create BytesIO object for the document libraries to read
        from io import BytesIO
        doc_file = BytesIO(binary_content)
        
        extracted_text = ""
        
        # Try to identify if it's a .docx file by examining the first few bytes
        # .docx files are actually zip files and start with PK signature
        is_docx = binary_content[:4] == b'PK\x03\x04'
        
        if docx_available and is_docx:
            # Use python-docx for .docx files
            doc = docx.Document(doc_file)
            
            # Process document structure and convert to markdown
            
            # Extract title if available
            if doc.paragraphs and doc.paragraphs[0].style.name.startswith('Heading'):
                extracted_text += f"# {doc.paragraphs[0].text}\n\n"
                start_idx = 1
            else:
                start_idx = 0
            
            # Process paragraphs
            for para in doc.paragraphs[start_idx:]:
                # Handle headings
                if para.style.name.startswith('Heading 1'):
                    extracted_text += f"# {para.text}\n\n"
                elif para.style.name.startswith('Heading 2'):
                    extracted_text += f"## {para.text}\n\n"
                elif para.style.name.startswith('Heading 3'):
                    extracted_text += f"### {para.text}\n\n"
                # Handle lists
                elif para.style.name.startswith('List'):
                    extracted_text += f"- {para.text}\n"
                # Normal paragraphs
                elif para.text.strip():
                    # Check for bold, italic, etc.
                    formatted_text = ""
                    for run in para.runs:
                        text = run.text
                        if run.bold and run.italic:
                            text = f"***{text}***"
                        elif run.bold:
                            text = f"**{text}**"
                        elif run.italic:
                            text = f"*{text}*"
                        formatted_text += text
                    
                    extracted_text += f"{formatted_text}\n\n"
            
            # Process tables
            for table in doc.tables:
                # Create markdown table
                for i, row in enumerate(table.rows):
                    for cell in row.cells:
                        extracted_text += f"| {cell.text} "
                    extracted_text += "|\n"
                    
                    # Add separator after header row
                    if i == 0:
                        extracted_text += "|" + "---|" * len(row.cells) + "\n"
                
                extracted_text += "\n"
            
        elif textract_available:
            # Fallback to textract for other document types including .doc
            # Save binary content to a temporary file
            import tempfile
            import os
            
            temp_fd, temp_path = tempfile.mkstemp(suffix='.doc')
            try:
                with os.fdopen(temp_fd, 'wb') as tmp:
                    tmp.write(binary_content)
                
                # Use textract to extract text
                doc_text = textract.process(temp_path).decode('utf-8')
                
                # Basic formatting for paragraphs
                paragraphs = doc_text.split('\n\n')
                for para in paragraphs:
                    if para.strip():
                        extracted_text += f"{para.strip()}\n\n"
            finally:
                # Clean up the temp file
                os.unlink(temp_path)
        else:
            return "Word document text extraction failed. Required libraries not installed."
        
        # Clean up the text
        extracted_text = clean_text(extracted_text)
        
        return extracted_text
            
    except Exception as e:
        logger.error(f"Error converting Word document to Markdown: {str(e)}")
        return f"Error extracting text from Word document: {str(e)}"

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
            return convert_pdf_to_markdown(content)
            
        # Word documents - use exact matching for MIME types and extension checking for simple types
        elif (file_type == "application/msword" or 
              file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or
              file_type.endswith(".docx") or file_type.endswith(".doc") or 
              file_type == "word"):
            return convert_word_to_markdown(content)
            
        # Excel files - use exact matching for MIME types and extension checking for simple types
        elif (file_type == "application/vnd.ms-excel" or
              file_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" or
              file_type.endswith(".xlsx") or file_type.endswith(".xls") or
              file_type == "excel"):
            return convert_excel_to_json(content)
            
        # Text files
        elif any(x in file_type for x in ["text/plain", "text/csv", "text/markdown", "text/tab-separated-values",
                                         "text/", "txt", "csv", "md", "tsv"]):
            return base64_to_text(content)
            
        # PowerPoint files
        elif any(x in file_type for x in ["application/vnd.ms-powerpoint", 
                                         "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                         "powerpoint", "ppt", "pptx"]):
            return convert_ppt_to_markdown(content)
            
        # HTML content
        elif "text/html" in file_type or "html" in file_type:
            return html_to_markdown(content)
            
        # Default case - return content as is
        else:
            return ""
    
    except Exception as e:
        logger.error(f"Error extracting text from {file_type} attachment: {str(e)}")
        return ""

def base64_to_text(base64_string: str, encoding: str = 'utf-8') -> str:
    """
    Convert a base64-encoded string to plain text.
    
    Args:
        base64_string: The base64-encoded string to decode
        encoding: The text encoding to use (default: utf-8)
        
    Returns:
        Decoded plain text
    """
    if not base64_string:
        return ""
    
    try:
        # Remove any padding or whitespace that might affect decoding
        base64_string = base64_string.strip()
        
        # Handle potential URL-safe base64 encoding
        base64_string = base64_string.replace('-', '+').replace('_', '/')
        
        # Add padding if necessary
        padding = len(base64_string) % 4
        if padding:
            base64_string += '=' * (4 - padding)
            
        # Decode the base64 string to bytes
        decoded_bytes = base64.b64decode(base64_string)
        
        # Convert bytes to string using the specified encoding
        decoded_text = decoded_bytes.decode(encoding)
        
        return decoded_text
        
    except Exception as e:
        logger.error(f"Error decoding base64 string: {str(e)}")
        return f"Failed to decode base64 string: {str(e)}"
