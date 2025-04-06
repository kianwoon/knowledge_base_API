#!/usr/bin/env python3
"""
Qdrant mail models for the Mail Analysis API.
"""

from typing import List, Dict, Optional, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

from app.models.email import EmailSchema, EmailAnalysis, AttachmentAnalysis


class QdrantAttachment(BaseModel):
    """Qdrant attachment model for storing in vector database."""
    
    filename: str
    mimetype: str
    size: int
    content_base64: str


class QdrantEmailEntry(BaseModel):
    """Qdrant email entry model for storing in vector database."""
    
    type: Literal["email"] = "email"
    job_id: str
    owner: str
    sender: str
    subject: str
    date: str  # ISO format (YYYY-MM-DD)
    has_attachments: bool
    folder: str
    tags: List[str] = []
    analysis_status: str
    status: str
    source: Literal["email"] = "email"
    raw_text: str
    attachments: List[QdrantAttachment] = []
    attachment_count: int = 0
    
    @classmethod
    def from_email_schema(cls, email: EmailSchema, job_id: str, owner: str, folder: str = "Inbox"):
        """Create a QdrantEmailEntry from an EmailSchema."""
        attachments = []
        for attachment in email.attachments:
            attachments.append(QdrantAttachment(
                filename=attachment.filename,
                mimetype=attachment.content_type,
                size=attachment.size,
                content_base64=attachment.content
            ))
        
        return cls(
            job_id=job_id,
            owner=owner,
            sender=email.from_.email,
            subject=email.subject,
            date=email.date.date().isoformat(),
            has_attachments=len(email.attachments) > 0,
            folder=folder,
            analysis_status="pending",
            status="new",
            raw_text=email.body_text or "",
            attachments=attachments,
            attachment_count=len(attachments)
        )


class QdrantQueryCriteria(BaseModel):
    """Qdrant query criteria model for storing in vector database."""
    
    folder: Optional[str] = None
    from_date: Optional[str] = None  # ISO format (YYYY-MM-DD)
    to_date: Optional[str] = None  # ISO format (YYYY-MM-DD)
    keywords: List[str] = []


class QdrantQueryCriteriaEntry(BaseModel):
    """Qdrant query criteria entry model for storing in vector database."""
    
    type: Literal["query_criteria"] = "query_criteria"
    job_id: str
    owner: str
    query_criteria: QdrantQueryCriteria


class QdrantChartDataItem(BaseModel):
    """Qdrant chart data item model for storing in vector database."""
    
    tag: str
    cluster: str
    subject: str


class QdrantAnalysisChartEntry(BaseModel):
    """Qdrant analysis chart entry model for storing in vector database."""
    
    type: Literal["analysis_chart"] = "analysis_chart"
    job_id: str
    owner: str
    status: str
    chart_data: List[QdrantChartDataItem] = []
    
    @classmethod
    def from_email_analysis(cls, analysis: EmailAnalysis, job_id: str, owner: str):
        """Create a QdrantAnalysisChartEntry from an EmailAnalysis."""
        # Extract tags from topics and create chart data items
        chart_data = []
        for topic in analysis.topics:
            chart_data.append(QdrantChartDataItem(
                tag=topic,
                cluster=analysis.intent,  # Use intent as cluster
                subject=analysis.subject
            ))
        
        return cls(
            job_id=job_id,
            owner=owner,
            status="completed",
            chart_data=chart_data
        )