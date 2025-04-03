#!/usr/bin/env python3
"""
Email data models for the Mail Analysis API.
"""

from typing import List, Dict, Optional, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
import base64

from app.core.config import config, localize_datetime


class EmailAddress(BaseModel):
    """Email address model."""
    
    name: Optional[str] = None
    email: EmailStr


class EmailAttachment(BaseModel):
    """Email attachment model supporting binary files (PDF, images, etc)."""
    
    filename: str = Field(..., pattern=r"^[\w,\s-]+\.[A-Za-z]{3,4}$")
    content_type: str = Field(..., examples=["application/pdf", "image/png", "text/plain"])
    content: str = Field(..., description="Base64 encoded binary content")
    size: int
    
    @field_validator("size")
    @classmethod
    def validate_size(cls, v):
        """Validate attachment size."""
        max_size = config.get("app", {}).get("max_attachment_size", "25MB")
        max_size_bytes = 25 * 1024 * 1024  # Default to 25MB
        
        # If max_size is a string (e.g., "25MB"), parse it
        if isinstance(max_size, str):
            # Parse size string (e.g., "25MB")
            unit_map = {
                "B": 1,
                "KB": 1024,
                "MB": 1024 * 1024,
                "GB": 1024 * 1024 * 1024
            }
            
            # Extract numeric part and unit
            import re
            match = re.match(r'^(\d+)([A-Za-z]+)$', max_size)
            if match:
                value, unit = match.groups()
                if unit in unit_map:
                    max_size_bytes = int(value) * unit_map[unit]
        elif isinstance(max_size, (int, float)):
            max_size_bytes = int(max_size)
            
        # Validate the attachment size
        if v > max_size_bytes:
            raise ValueError(f"Attachment size exceeds maximum of {max_size_bytes} bytes")
        return v
    
    @field_validator("content")
    @classmethod
    def validate_content(cls, v, values):
        """Validate attachment content and type."""
        # Validate base64 encoding
        try:
            decoded = base64.b64decode(v)
        except Exception:
            raise ValueError("Invalid base64 encoding for attachment content")
            
        # Validate content type matches file extension
        if "content_type" in values.data and "filename" in values.data:
            mime_type = values.data["content_type"].lower()
            extension = values.data["filename"].split(".")[-1].lower()
            
            # Map common extensions to MIME types
            mime_map = {
                "pdf": "application/pdf",
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "txt": "text/plain",
                "csv": "text/csv"
            }
            
            if extension in mime_map and mime_type != mime_map[extension]:
                raise ValueError(f"Content type {mime_type} does not match file extension .{extension}")
                
        return v


class EmailSchema(BaseModel):
    """Email schema for API input."""
    
    message_id: str
    subject: str
    from_: EmailAddress = Field(..., alias="from")
    to: List[EmailAddress]
    cc: Optional[List[EmailAddress]] = []
    bcc: Optional[List[EmailAddress]] = []
    date: datetime
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    attachments: Optional[List[EmailAttachment]] = []
    headers: Optional[Dict[str, str]] = {}
    
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {"title": "Email Schema"}
    }
    
    @model_validator(mode='after')
    def localize_date(self):
        """Ensure date has timezone information."""
        if self.date and self.date.tzinfo is None:
            self.date = localize_datetime(self.date)
        return self


class AttachmentAnalysis(BaseModel):
    """Attachment analysis result model."""
    
    filename: str
    content_type: str
    size: int
    content_summary: str
    sentiment: Optional[str] = None
    topics: List[str] = []
    entities: List[Dict[str, str]] = []
    needSave: bool = Field(default=False, description="Indicates if attachment should be saved")


class EmailAnalysis(BaseModel):
    """Email analysis result model."""
    
    message_id: str
    subject: str
    date: datetime
    summary: str
    sentiment: str
    topics: List[str]
    action_items: List[Dict[str, Any]]
    entities: List[Dict[str, str]]
    intent: str
    importance_score: float
    attachment_analyses: List[AttachmentAnalysis] = []
    processing_time: float
    job_id: str
    source_category: Literal["External", "Internal"]
    sensitivity_level: Literal["Public", "Normal", "Confidential", "Highly Confidential"]
    response_required: bool
    reference_required: bool
    departments: List[str]
    agent_role: Optional[str] = "Admin"
    
    @model_validator(mode='after')
    def localize_date(self):
        """Ensure date has timezone information."""
        if self.date and self.date.tzinfo is None:
            self.date = localize_datetime(self.date)
        return self


class JobResponse(BaseModel):
    """Job response model."""
    
    job_id: str
    status: str
    status_url: str


class StatusResponse(BaseModel):
    """Job status response model."""
    
    job_id: str
    status: str
    results_url: Optional[str] = None
    error: Optional[str] = None


class AnalysisResponse(BaseModel):
    """Analysis response model."""
    
    analysis: EmailAnalysis


class SubjectAnalysisRequest(BaseModel):
    """Email subject analysis request model."""
    
    subjects: List[str] = Field(..., description="List of email subject lines to analyze")
    min_confidence: Optional[float] = Field(0.7, description="Minimum confidence threshold for analysis")


class SubjectAnalysisResult(BaseModel):
    """Result model for a single subject analysis."""
    
    tag: str = Field(..., description="Business category (e.g., timesheet, approval, staffing, sow, finance-review, general)")
    cluster: str = Field(..., description="High-level grouping or topic (e.g., month, client, project, system name)")
    subject: str = Field(..., description="Original subject line")


class BatchSubjectAnalysisResponse(BaseModel):
    """Response model for batch subject analysis."""
    
    results: List[SubjectAnalysisResult]


class ErrorResponse(BaseModel):
    """Error response model."""
    
    error: Dict[str, Any]
