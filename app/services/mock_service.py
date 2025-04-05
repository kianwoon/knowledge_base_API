#!/usr/bin/env python3
"""
Mock service module for the Mail Analysis API.
This module provides mock implementations of external services for testing.
"""

import json
import asyncio
from typing import Dict, List, Any
from datetime import datetime
from loguru import logger

from app.core.config import localize_datetime


# Import the mock subject analysis functionality
from app.services.mock_subject_service import analyze_subjects


class MockChatCompletionResponse:
    """Mock response for testing without real OpenAI API calls."""
    def __init__(self, analysis_type="email_analysis"):
        """Initialize mock response."""
        if analysis_type == "email_analysis":
            content = {
                "summary": "This is a test email requesting information about a project deadline.",
                "sentiment": "neutral",
                "topics": ["project deadline", "meeting request", "status update"],
                "action_items": [
                    {"text": "Schedule a meeting next week", "priority": "medium"},
                    {"text": "Prepare status report", "priority": "high"},
                    {"text": "Share project timeline", "priority": "low"}
                ],
                "entities": [
                    {"name": "John Doe", "type": "person"},
                    {"name": "Project X", "type": "project"}
                ],
                "intent": "request",
                "importance_score": 0.7
            }
        elif analysis_type == "attachment_analysis":
            content = {
                "content_summary": "This is a test document containing project requirements and specifications.",
                "sentiment": "neutral",
                "topics": ["project requirements", "specifications", "timeline"],
                "entities": [
                    {"name": "Project X", "type": "project"},
                    {"name": "Technical Team", "type": "organization"}
                ]
            }
        else:
            content = {
                "summary": "Generic text analysis result.",
                "sentiment": "neutral",
                "topics": ["general", "information"]
            }
            
        self.choices = [
            type('obj', (object,), {
                'message': type('obj', (object,), {
                    'content': json.dumps(content)
                })
            })
        ]
        self.usage = type('obj', (object,), {'total_tokens': 350})


class MockOpenAIService:
    """Mock service for OpenAI API."""
    
    def __init__(self):
        """Initialize mock OpenAI service."""
        logger.info("Initializing MockOpenAIService")
    
    async def analyze_subjects(self, subjects: List[str], min_confidence: float = 0.7) -> List[Dict[str, Any]]:
        """
        Analyze a list of email subject lines using mock responses.
        
        Args:
            subjects: List of email subject lines
            min_confidence: Minimum confidence threshold for analysis
            
        Returns:
            List of analysis results for each subject
        """
        logger.info(f"Mock analyzing {len(subjects)} email subjects")
        
        # Simulate API latency
        await asyncio.sleep(0.5)
        
        # Use the mock subject analysis function
        results = analyze_subjects(subjects)
        
        return results
    
    async def analyze_text(self, text: str, analysis_type: str) -> Dict[str, Any]:
        """
        Analyze text using mock responses.
        
        Args:
            text: Text to analyze
            analysis_type: Type of analysis to perform
            
        Returns:
            Analysis results
        """
        logger.info(f"Mock analyzing text with analysis type: {analysis_type}")
        
        # Simulate API latency
        await asyncio.sleep(0.5)
        
        # Create mock response
        response = MockChatCompletionResponse(analysis_type)
        
        # Parse response
        try:
            result = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            # Fallback to raw text if not valid JSON
            result = {"raw_response": response.choices[0].message.content}
            
        # Add metadata
        result["_metadata"] = {
            "model": "gpt-3.5-turbo",
            "tokens": response.usage.total_tokens,
            "elapsed_time": 0.5
        }
        
        return result
    
    async def analyze_email(self, email_data: Dict[str, Any], job_id: str, trace_id: str) -> Dict[str, Any]:
        """
        Analyze email data using mock responses.
        
        Args:
            email_data: Email data
            
        Returns:
            Analysis results
        """
        logger.info(f"Mock analyzing email, job_id: {job_id}, trace_id: {trace_id}")
        
        # Extract email text (simplified for mock)
        email_text = f"Subject: {email_data['subject']}\nFrom: {email_data['from']['email']}\nBody: (mock email body)"
        
        # Analyze email text
        email_analysis = await self.analyze_text(email_text, "email_analysis")
        
        # Analyze attachments
        attachment_analyses = []
        
        for attachment in email_data.get("attachments", []):
            try:
                # Mock attachment analysis
                attachment_analysis = await self.analyze_text("Mock attachment content", "attachment_analysis")
                
                # Add attachment metadata
                attachment_analysis["filename"] = attachment["filename"]
                attachment_analysis["content_type"] = attachment["content_type"]
                attachment_analysis["size"] = attachment["size"]
                
                attachment_analyses.append(attachment_analysis)
            except Exception as e:
                logger.error(f"Error in mock analysis of attachment {attachment['filename']}: {str(e)}")
                
                # Add basic attachment info
                attachment_analyses.append({
                    "filename": attachment["filename"],
                    "content_type": attachment["content_type"],
                    "size": attachment["size"],
                    "content_summary": f"Error analyzing attachment: {str(e)}",
                    "sentiment": None,
                    "topics": [],
                    "entities": []
                })
        
        # Determine source category (simplified for mock)
        source_category = "External"
        if "@company.com" in email_data.get("from", {}).get("email", ""):
            source_category = "Internal"
        
        # Format entities to match expected schema
        def format_entities(entities):
            if isinstance(entities, list):
                return entities
            return []
            
        # Combine results
        result = {
            "message_id": email_data["message_id"],
            "subject": email_data["subject"],
            "date": localize_datetime(email_data["date"]).isoformat() if isinstance(email_data["date"], datetime) else email_data["date"],
            "summary": email_analysis.get("summary", ""),
            "sentiment": email_analysis.get("sentiment", "neutral"),
            "topics": email_analysis.get("topics", []),
            "action_items": email_analysis.get("action_items", []),
            "entities": format_entities(email_analysis.get("entities", [])),
            "intent": email_analysis.get("intent", "information_sharing"),
            "importance_score": email_analysis.get("importance_score", 0.5),
            "attachment_analyses": attachment_analyses,
            "processing_time": email_analysis.get("_metadata", {}).get("elapsed_time", 0),
            # Additional required fields
            "source_category": source_category,
            "sensitivity_level": "Normal",
            "response_required": True,
            "departments": ["General"],
            "agent_role": "HR"
        }
        
        return result
