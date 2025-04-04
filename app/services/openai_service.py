#!/usr/bin/env python3
"""
OpenAI service module for the Mail Analysis API.
"""

import os
import re
import time
import json
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from openai import AsyncOpenAI
from loguru import logger

from app.core.config import config, localize_datetime
from app.core.redis import redis_client
from app.services.mock_service import MockOpenAIService


class OpenAIKeyManager:
    """Manager for OpenAI API keys."""
    
    def __init__(self):
        """Initialize OpenAI key manager."""
        self.primary_key = config.get("openai", {}).get("api_key")
        self.backup_keys = config.get("openai", {}).get("backup_api_keys", "").split(",")
        
        # Use environment variable if available
        if os.environ.get("OPENAI_API_KEY"):
            self.primary_key = os.environ.get("OPENAI_API_KEY")
            
        if os.environ.get("OPENAI_BACKUP_API_KEYS"):
            self.backup_keys = os.environ.get("OPENAI_BACKUP_API_KEYS").split(",")
        
    async def get_api_key(self) -> str:
        """
        Get an available API key.
        
        Returns:
            OpenAI API key
        
        Raises:
            Exception: If no API keys are available
        """
        try:
            # Ensure Redis client is connected
            if redis_client.client is None:
                await redis_client.connect()
                
            # Check if primary key is rate limited
            primary_limited = await redis_client.get("openai_limited:primary")
            
            if not primary_limited and self.primary_key:
                return self.primary_key
                
            # Try backup keys
            for i, key in enumerate(self.backup_keys):
                if key and not await redis_client.get(f"openai_limited:backup_{i}"):
                    return key
                    
            # All keys are rate limited
            raise Exception("All OpenAI API keys are currently rate limited")
        except Exception as e:
            logger.error(f"Error getting API key: {str(e)}")
            # If Redis fails, return primary key as fallback
            if self.primary_key:
                return self.primary_key
            elif self.backup_keys and self.backup_keys[0]:
                return self.backup_keys[0]
            else:
                raise Exception("No API keys available and Redis connection failed")
        
    async def mark_key_limited(self, key: str, duration: int = 60):
        """
        Mark an API key as rate limited.
        
        Args:
            key: API key
            duration: Duration in seconds to mark as limited
        """
        try:
            # Ensure Redis client is connected
            if redis_client.client is None:
                await redis_client.connect()
                
            if key == self.primary_key:
                await redis_client.setex("openai_limited:primary", duration, "1")
                logger.warning("Primary OpenAI API key rate limited")
            else:
                for i, backup_key in enumerate(self.backup_keys):
                    if key == backup_key:
                        await redis_client.setex(f"openai_limited:backup_{i}", duration, "1")
                        logger.warning(f"Backup OpenAI API key {i} rate limited")
                        break
        except Exception as e:
            logger.error(f"Error marking key as limited: {str(e)}")
            # Continue execution even if Redis operation fails


class OpenAICostTracker:
    """Tracker for OpenAI API costs."""
    
    def __init__(self):
        """Initialize OpenAI cost tracker."""
        self.model_costs = {
            "gpt-4": 0.03,  # $0.03 per 1K tokens
            "gpt-4o": 0.01,  # $0.01 per 1K tokens
            "gpt-4o-mini": 0.00015,  # $0.00015 per 1K tokens ($0.15 per 1M tokens)
        }
        
    def calculate_cost(self, model: str, tokens: int) -> float:
        """
        Calculate cost for API usage.
        
        Args:
            model: Model name
            tokens: Number of tokens
            
        Returns:
            Cost in USD
        """
        # Get cost per 1K tokens for model
        cost_per_1k = self.model_costs.get(model, 0.01)  # Default to $0.01 per 1K tokens
        
        # Calculate cost
        return (tokens / 1000) * cost_per_1k
        
    async def track_usage(self, model: str, tokens: int):
        """
        Track API usage.
        
        Args:
            model: Model name
            tokens: Number of tokens
        """
        try:
            # Ensure Redis client is connected
            if redis_client.client is None:
                await redis_client.connect()
                
            # Calculate cost
            cost = self.calculate_cost(model, tokens)
            
            # Track monthly cost
            await redis_client.incrby("openai:monthly_tokens", tokens)
            await redis_client.incrbyfloat("openai:monthly_cost", cost)
            
            # Set expiry if not already set (31 days)
            if not await redis_client.ttl("openai:monthly_cost"):
                await redis_client.expire("openai:monthly_cost", 31 * 24 * 60 * 60)
                await redis_client.expire("openai:monthly_tokens", 31 * 24 * 60 * 60)
            
            # Log usage
            logger.info(f"OpenAI API usage: {model}, {tokens} tokens, ${cost:.4f}")
        except Exception as e:
            logger.error(f"Error tracking usage: {str(e)}")
            # Continue execution even if Redis operation fails
        
    async def check_limit(self) -> bool:
        """
        Check if monthly cost limit has been reached.
        
        Returns:
            True if within limit, False otherwise
        """
        try:
            # Ensure Redis client is connected
            if redis_client.client is None:
                await redis_client.connect()
                
            # Get monthly cost limit
            monthly_limit = config.get("openai", {}).get("monthly_cost_limit", 1000)
            
            # Get current monthly cost
            current_cost = float(await redis_client.get("openai:monthly_cost") or 0)
            
            # Check if limit reached
            if current_cost >= monthly_limit:
                logger.warning(f"OpenAI API monthly cost limit reached: ${current_cost:.2f}/{monthly_limit:.2f}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error checking cost limit: {str(e)}")
            return True  # Default to allowing API calls if Redis check fails
        
    async def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics.
        
        Returns:
            Dictionary with usage statistics
        """
        try:
            # Ensure Redis client is connected
            if redis_client.client is None:
                await redis_client.connect()
                
            # Get monthly cost limit
            monthly_limit = config.get("openai", {}).get("monthly_cost_limit", 1000)
            
            # Get current usage
            current_cost = float(await redis_client.get("openai:monthly_cost") or 0)
            current_tokens = int(await redis_client.get("openai:monthly_tokens") or 0)
            
            # Calculate percentage of limit
            percentage = (current_cost / monthly_limit) * 100 if monthly_limit > 0 else 0
            
            return {
                "monthly_cost": current_cost,
                "monthly_tokens": current_tokens,
                "monthly_limit": monthly_limit,
                "percentage": percentage,
                "remaining": monthly_limit - current_cost
            }
        except Exception as e:
            logger.error(f"Error getting usage stats: {str(e)}")
            # Return default values if Redis operation fails
            return {
                "monthly_cost": 0,
                "monthly_tokens": 0,
                "monthly_limit": config.get("openai", {}).get("monthly_cost_limit", 1000),
                "percentage": 0,
                "remaining": config.get("openai", {}).get("monthly_cost_limit", 1000)
            }


def sanitize_prompt(prompt: str) -> str:
    """
    Sanitize prompt to prevent prompt injection.
    
    Args:
        prompt: User-provided prompt
        
    Returns:
        Sanitized prompt
    """
    # Remove potential system instruction overrides
    sanitized = re.sub(r"(^|\n)system:", "", prompt)
    
    # Remove potential role changes
    sanitized = re.sub(r"(^|\n)(user|assistant|system):", "", sanitized)
    
    # Remove markdown code block syntax that might be used to hide instructions
    sanitized = re.sub(r"```.*?```", "", sanitized, flags=re.DOTALL)
    
    return sanitized


class OpenAIService:
    """Service for interacting with OpenAI API."""
    
    def __init__(self):
        """Initialize OpenAI service."""
        self.key_manager = OpenAIKeyManager()
        self.cost_tracker = OpenAICostTracker()
        
    async def analyze_text(self, text: str, analysis_type: str) -> Dict[str, Any]:
        """
        Analyze text using OpenAI API.
        
        Args:
            text: Text to analyze
            analysis_type: Type of analysis to perform
            
        Returns:
            Analysis results
        """
        logger.info(f"Starting analysis of text with type: {analysis_type}")
        logger.debug(f"Text length: {len(text)} characters")
        
        try:
            # Check cost limit
            if not await self.cost_tracker.check_limit():
                logger.warning("OpenAI API monthly cost limit reached")
                raise Exception("OpenAI API monthly cost limit reached")
                
            # Get API key
            api_key = await self.key_manager.get_api_key()
            logger.debug("Successfully retrieved API key")
            
            # Initialize OpenAI client with API key
            client = AsyncOpenAI(api_key=api_key)
            logger.debug("Initialized AsyncOpenAI client")
            
            # Get model
            model_choices = config.get("openai", {}).get("model_choices", ["gpt-4o-mini"])
            model = model_choices[0]  # Use first model in list
            logger.info(f"Using model: {model}")
            
            # Get max tokens
            max_tokens = config.get("openai", {}).get("max_tokens_per_request", 40960)
            logger.debug(f"Max tokens set to: {max_tokens}")
            
            # Prepare prompt based on analysis type
            system_prompt = self._get_system_prompt(analysis_type)
            logger.debug(f"System prompt length: {len(system_prompt)} characters")
            
            # Sanitize user text
            sanitized_text = sanitize_prompt(text)
            logger.debug(f"Sanitized text length: {len(sanitized_text)} characters")
            
            # Call OpenAI API
            logger.info(f"Calling OpenAI API with model {model} for {analysis_type}")
            start_time = time.time()
            
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": sanitized_text}
                    ],
                    max_tokens=max_tokens,
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                logger.info(f"OpenAI API call successful for {analysis_type}")
                logger.info(f"Response: {response}")
            except Exception as api_error:
                logger.error(f"OpenAI API call failed: {str(api_error)}")
                raise
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            
            # Track usage
            try:
                await self.cost_tracker.track_usage(
                    model,
                    response.usage.total_tokens
                )
            except Exception as e:
                logger.warning(f"Failed to track usage: {str(e)}")
            
            # Parse response
            try:
                result = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError:
                # Fallback to raw text if not valid JSON
                result = {"raw_response": response.choices[0].message.content}
                
            # Add metadata
            result["_metadata"] = {
                "model": model,
                "tokens": response.usage.total_tokens,
                "elapsed_time": elapsed_time
            }
            
            return result
            
        except Exception as e:
            # Check if it's a rate limit error based on error message
            error_message = str(e).lower()
            if "rate limit" in error_message:
                # Mark key as rate limited
                await self.key_manager.mark_key_limited(api_key)
                
                # Try again with a different key
                return await self.analyze_text(text, analysis_type)
            elif "api" in error_message and "error" in error_message:
                logger.error(f"OpenAI API error: {str(e)}")
                raise
            else:
                # For other types of errors
                logger.error(f"Error analyzing text: {str(e)}")
                raise
            
    async def analyze_subjects(self, subjects: List[str], min_confidence: float = 0.7, job_id: str = None, trace_id: str = None) -> List[Dict[str, Any]]:
        """
        Analyze a list of email subject lines.
        
        Args:
            subjects: List of email subject lines
            min_confidence: Minimum confidence threshold for analysis
            job_id: Job ID (optional)
            trace_id: Trace ID (optional)
            
        Returns:
            List of analysis results for each subject
        """
        logger.info(f"Starting analysis of {len(subjects)} email subjects, job_id: {job_id}, trace_id: {trace_id}")
        
        try:
            # Check cost limit
            if not await self.cost_tracker.check_limit():
                logger.warning("OpenAI API monthly cost limit reached")
                raise Exception("OpenAI API monthly cost limit reached")
                
            # Get API key
            api_key = await self.key_manager.get_api_key()
            logger.debug("Successfully retrieved API key")
            
            # Initialize OpenAI client with API key
            client = AsyncOpenAI(api_key=api_key)
            logger.debug("Initialized AsyncOpenAI client")
            
            # Get model
            model_choices = config.get("openai", {}).get("model_choices", ["gpt-4o-mini"])
            model = model_choices[0]  # Use first model in list
            logger.info(f"Using model: {model}")
            
            # Get max tokens
            max_tokens = config.get("openai", {}).get("max_tokens_per_request", 40960)
            logger.debug(f"Max tokens set to: {max_tokens}")
            
            # Prepare prompt for subject analysis
            system_prompt = self._get_system_prompt("subject_analysis")
            
            # Format the subjects as a list in the prompt
            subjects_text = "\n".join([f"- \"{subject}\"" for subject in subjects])
            
            # Call OpenAI API
            logger.info(f"Calling OpenAI API with model {model} for subject analysis")
            start_time = time.time()
            
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": subjects_text}
                    ],
                    max_tokens=max_tokens,
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                logger.info(f"OpenAI API call successful for subject analysis")
            except Exception as api_error:
                logger.error(f"OpenAI API call failed: {str(api_error)}")
                raise
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            
            # Track usage
            try:
                await self.cost_tracker.track_usage(
                    model,
                    response.usage.total_tokens
                )
            except Exception as e:
                logger.warning(f"Failed to track usage: {str(e)}")
            
            # Parse response
            try:
                result = json.loads(response.choices[0].message.content)
                
                # Ensure the response has the expected structure
                if "results" not in result or not isinstance(result["results"], list):
                    logger.warning("Unexpected response format from OpenAI API")
                    result = {"results": []}
                
                # Add metadata
                # result["_metadata"] = {
                #     "model": model,
                #     "tokens": response.usage.total_tokens,
                #     "elapsed_time": elapsed_time
                # }
                result["job_id"] = job_id

                # Add job_id to each result item if provided
                # if job_id:
                #     for item in result.get("results", []):
                #         item["job_id"] = job_id
                
                return result
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON response from OpenAI API")
                raise Exception("Invalid response format from OpenAI API")
                
        except Exception as e:
            # Check if it's a rate limit error based on error message
            error_message = str(e).lower()
            if "rate limit" in error_message:
                # Mark key as rate limited
                await self.key_manager.mark_key_limited(api_key)
                
                # Try again with a different key
                return await self.analyze_subjects(subjects, min_confidence, job_id, trace_id)
            else:
                # For other types of errors
                logger.error(f"Error analyzing subjects: {str(e)}")
                raise
    
    def _get_system_prompt(self, analysis_type: str) -> str:
        """
        Get system prompt for analysis type.
        
        Args:
            analysis_type: Type of analysis to perform
            
        Returns:
            System prompt
        """
        if analysis_type == "subject_analysis":
            return """
            You are an AI assistant that analyzes email subject lines. Your task is to categorize each subject line and identify its business context.
            
            For each subject line, provide the following information:
            - tag: the business category (choose one from: timesheet, approval, staffing, sow, finance-review, general)
            - cluster: a high-level grouping or topic (e.g., month, client, project, system name) — avoid personal names or email addresses
            - subject: the original subject line
            
            Analyze the provided email subject lines and return a JSON array where each item includes these three fields.
            
            Example response format:
            {
              "results": [
                {
                  "tag": "timesheet",
                  "cluster": "March 2024",
                  "subject": "Timesheet approval for March 2024"
                },
                {
                  "tag": "approval",
                  "cluster": "Project X",
                  "subject": "Please approve design for Project X"
                }
              ]
            }
            
            Return your analysis as a valid JSON object with a "results" array containing an entry for each subject line.
            """
        elif analysis_type == "email_analysis":
            return """
            You are an AI assistant that analyzes emails. Your task is to extract key information from the email and provide a structured analysis.
            
            Analyze the email and provide the following information in JSON format:
            - summary: A concise summary of the email (1-2 sentences)
            - sentiment: The overall sentiment of the email (positive, negative, neutral)
            - topics: A list of main topics discussed in the email (3-5 topics)
            - action_items: A list of action items or requests made in the email. Each action item should be an object with the following fields:
              * description: A description of the action item
              * priority: The priority of the action item (default to "medium")
              For example: [{"description": "Schedule a meeting with the team", "priority": "high"}]
            - entities: A list of entities mentioned in the email. Each entity should be an object with 'name' and 'type' fields. For example: [{"name": "John Doe", "type": "person"}, {"name": "Acme Corp", "type": "organization"}]
            - intent: The primary intent of the email (information_sharing, request, follow_up, etc.)
            - importance_score: A score from 0 to 1 indicating the importance of the email
            - sensitivity_level: The sensitivity level of the email (Public, Normal, Confidential, or Highly Confidential)
            - response_required: A boolean indicating whether the email requires a response (true or false)
            - reference_required: A boolean indicating whether the email requires to save to knowledge database for future reference (true or false)
            - departments: A list of departments that should handle this email (
                    IT: ["software", "hardware", "server", "network", "computer", "technology", "technical", "it"]
                    HR: ["hiring", "recruitment", "employee", "benefits", "hr", "personnel", "training", "onboarding"]
                    Finance: ["budget", "payment", "invoice", "financial", "accounting", "expense", "finance", "cost"]
                    Legal: ["contract", "agreement", "compliance", "law", "legal", "policy", "regulation", "terms"]
                    Marketing: ["campaign", "advertisement", "social media", "marketing", "promotion", "brand", "market"]
                    Sales: ["customer", "client", "sale", "opportunity", "lead", "deal", "revenue", "prospect"]
                    Operations: ["operations", "logistics", "supply chain", "procurement", "facility", "warehouse"]
                    Product: ["product", "feature", "roadmap", "design", "user experience", "development", "release"])
            - agent_role: The role of the agent who should handle this email ( 
                    "HR": "Employee onboarding, benefits, leave, recruitment, etc.",
                    "Admin": "Office supplies, facility requests, travel, visitor handling",
                    "Finance": "Budget approvals, forecasts, internal audits",
                    "Billing": "Invoices, reimbursements, vendor payments",
                    "Legal": "Contracts, legal queries, policy enforcement",
                    "Sales": "Provide costing, Client acquisition, solution demos, sales support"
                ) or Admin if not applicable
            
            Return your analysis as a valid JSON object.
            """
            
        elif analysis_type == "attachment_analysis":
            return """
            You are an AI assistant that analyzes document content. Your task is to extract key information from the document and provide a structured analysis.
            
            Analyze the document and provide the following information in JSON format:
            - content_summary: A concise summary of the document content (2-3 sentences)
            - sentiment: The overall sentiment of the document (positive, negative, neutral)
            - topics: A list of main topics discussed in the document (3-5 topics)
            - entities: A list of entities mentioned in the document. Each entity should be an object with 'name' and 'type' fields. For example: [{"name": "John Doe", "type": "person"}, {"name": "Acme Corp", "type": "organization"}]
            
            Return your analysis as a valid JSON object.
            """
            
        else:
            return """
            You are an AI assistant that analyzes text. Your task is to extract key information from the text and provide a structured analysis.
            
            Analyze the text and provide the following information in JSON format:
            - summary: A concise summary of the text (1-2 sentences)
            - sentiment: The overall sentiment of the text (positive, negative, neutral)
            - topics: A list of main topics discussed in the text (3-5 topics)
            
            Return your analysis as a valid JSON object.
            """
            
    async def analyze_email(self, email_data: Dict[str, Any], job_id:str, trace_id:str ) -> Dict[str, Any]:
        """
        Analyze email data.
        
        Args:
            email_data: Email data
            
        Returns:
            Analysis results
        """
        message_id = email_data.get("message_id", "unknown")
        
        logger.info(f"Starting email analysis for message ID: {message_id}, job_id: {job_id}, trace_id: {trace_id}")
        
        try:
            # Log email data keys for debugging
            logger.info(f"Email data keys in OpenAI service: {list(email_data.keys())}, job_id: {job_id}, trace_id: {trace_id}")
            
            # Ensure 'from' field exists
            if 'from' not in email_data and 'from_' in email_data:
                logger.info(f"Converting 'from_' to 'from' for message ID: {message_id}, job_id: {job_id}, trace_id: {trace_id}")
                email_data['from'] = email_data['from_']
            elif 'from' not in email_data and 'from_' not in email_data:
                logger.error(f"Neither 'from' nor 'from_' found in email data for message ID: {message_id}, job_id: {job_id}, trace_id: {trace_id}")
                # Add a default 'from' field to prevent errors
                email_data['from'] = {'name': 'Unknown', 'email': 'unknown@example.com'}
            
            # Log from field for debugging
            try:
                from_field = email_data.get('from', {})
                logger.info(f"From field for message ID {message_id}, job_id: {job_id}, trace_id: {trace_id}: {from_field}")
            except Exception as e:
                logger.error(f"Error logging from field: {str(e)}, job_id: {job_id}, trace_id: {trace_id}")
            
            # Extract email text
            logger.info(f"Extracting email text for message ID: {message_id}, job_id: {job_id}, trace_id: {trace_id}")
            email_text = self._extract_email_text(email_data,job_id, trace_id)
            logger.debug(f"Extracted email text length: {len(email_text)} characters, job_id: {job_id}, trace_id: {trace_id}")
            
            # Analyze email text
            logger.info(f"Analyzing email text for message ID: {message_id}, job_id: {job_id}, trace_id: {trace_id}")
            email_analysis = await self.analyze_text(email_text, "email_analysis")
            logger.info(f"Email text analysis completed for message ID: {message_id}, job_id: {job_id}, trace_id: {trace_id}")
            
            # Analyze attachments
            attachment_analyses = []
            
            for attachment in email_data.get("attachments", []):
                try:
                    # Extract attachment text
                    attachment_text = self._extract_attachment_text(attachment,job_id, trace_id)
                    
                    # Analyze attachment text
                    attachment_analysis = await self.analyze_text(attachment_text, "attachment_analysis")
                    
                    # Add attachment metadata
                    attachment_analysis["filename"] = attachment["filename"]
                    attachment_analysis["content_type"] = attachment["content_type"]
                    attachment_analysis["size"] = attachment["size"]
                    
                    attachment_analyses.append(attachment_analysis)
                except Exception as e:
                    logger.error(f"Error analyzing attachment {attachment['filename']}: {str(e)}, job_id: {job_id}, trace_id: {trace_id}")
                    
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
                    
            # Combine results
            result = {
                "message_id": email_data["message_id"],
                "subject": email_data["subject"],
                "date": localize_datetime(email_data["date"]).isoformat() if isinstance(email_data["date"], datetime) else email_data["date"],
                "summary": email_analysis.get("summary", ""),
                "sentiment": email_analysis.get("sentiment", "neutral"),
                "topics": email_analysis.get("topics", []),
                "action_items": email_analysis.get("action_items", []),
                "entities": self._format_entities(email_analysis.get("entities", [])),
                "intent": email_analysis.get("intent", "information_sharing"),
                "importance_score": email_analysis.get("importance_score", 0.5),
                "attachment_analyses": attachment_analyses,
                "processing_time": email_analysis.get("_metadata", {}).get("elapsed_time", 0),
                "job_id": self._parse_job_id(email_data.get("job_id", "")),  # Parse job_id from email_data
                "source_category": self._determine_source_category(email_data),
                "sensitivity_level": email_analysis.get("sensitivity_level", "Normal"),
                "response_required": email_analysis.get("response_required", False),
                "reference_required": email_analysis.get("reference_required", False),
                "departments": email_analysis.get("departments", ["General"]),
                "agent_role": email_analysis.get("agent_role", "Admin")  # Get agent_role from AI model response
            }
            
            return result
        except Exception as e:
            logger.error(f"Error analyzing email: {str(e)}, job_id: {job_id}, trace_id: {trace_id}")
            # Return a basic result with error information
            return {
                "message_id": email_data.get("message_id", "unknown"),
                "subject": email_data.get("subject", "Unknown Subject"),
                "date": localize_datetime(email_data.get("date", datetime.now())).isoformat() if isinstance(email_data.get("date"), datetime) else email_data.get("date", localize_datetime(datetime.now()).isoformat()),
                "summary": f"Error analyzing email: {str(e)}",
                "sentiment": "",
                "topics": [],
                "action_items": [],
                "entities": [],
                "intent": "",
                "importance_score": 0.5,
                "attachment_analyses": [],
                "processing_time": 0,
                "job_id": self._parse_job_id(email_data.get("job_id", "")),  # Parse job_id from email_data
                "source_category": "",
                "sensitivity_level": "",
                "response_required": False,
                "departments": [],
                "agent_role": ""
            }
        
    def _extract_email_text(self, email_data: Dict[str, Any], job_str:str, trace_id:str) -> str:
        """
        Extract text from email data.
        
        Args:
            email_data: Email data
            
        Returns:
            Email text
        """
        message_id = email_data.get("message_id", "unknown")
        logger.info(f"Extracting email text for message ID: {message_id}")
        
        # Build email text
        text_parts = [
            f"Subject: {email_data['subject']}",
        ]
        logger.debug(f"Added subject: {email_data['subject']}")
        
        # Handle 'from' field which might be accessed as 'from' or 'from_' depending on dict conversion
        try:
            logger.debug(f"Processing 'from' field for message ID: {message_id}")
            if 'from' in email_data:
                from_field = email_data['from']
                logger.debug(f"Using 'from' field: {from_field}")
            elif 'from_' in email_data:
                from_field = email_data['from_']
                logger.debug(f"Using 'from_' field: {from_field}")
            else:
                from_field = {'name': 'Unknown', 'email': 'unknown@example.com'}
                logger.warning(f"No from field found for message ID: {message_id}, job_id: {job_id}, trace_id: {trace_id}, using default")
                
            text_parts.append(f"From: {from_field.get('name', 'Unknown') or 'Unknown'} <{from_field['email']}>")
            logger.debug(f"Added from: {from_field.get('name', 'Unknown') or 'Unknown'} <{from_field['email']}>")
        except Exception as e:
            logger.error(f"Error processing 'from' field for message ID {message_id}: {str(e)}, job_id: {job_id}, trace_id: {trace_id}")
            text_parts.append(f"From: Unknown <unknown@example.com>")
        
        # Add To recipients
        to_addresses = []
        for to in email_data['to']:
            name = to.get('name', 'Unknown')
            email = to['email']
            to_addresses.append(f"{name} <{email}>")
        text_parts.append(f"To: {', '.join(to_addresses)}")
        
        # Add date (handle both string and datetime)
        if isinstance(email_data['date'], datetime):
            # Ensure datetime has timezone info
            date_with_tz = localize_datetime(email_data['date'])
            text_parts.append(f"Date: {date_with_tz.isoformat()}")
        else:
            text_parts.append(f"Date: {email_data['date']}")
        
        # Add CC if present
        if email_data.get("cc"):
            cc_addresses = []
            for cc in email_data['cc']:
                name = cc.get('name', 'Unknown')
                email = cc['email']
                cc_addresses.append(f"{name} <{email}>")
            text_parts.append(f"CC: {', '.join(cc_addresses)}")
            
        # Add body
        if email_data.get("body_text"):
            text_parts.append("\n" + email_data["body_text"])
        elif email_data.get("body_html"):
            # Simple HTML to text conversion
            text = email_data["body_html"]
            text = re.sub(r"<[^>]*>", "", text)  # Remove HTML tags
            text = re.sub(r"\s+", " ", text)  # Normalize whitespace
            text_parts.append("\n" + text)
            
        # Add attachment info
        if email_data.get("attachments"):
            text_parts.append("\nAttachments:")
            for attachment in email_data["attachments"]:
                text_parts.append(f"- {attachment['filename']} ({attachment['content_type']}, {attachment['size']} bytes)")
                
        return "\n".join(text_parts)
        
    def _extract_attachment_text(self, attachment: Dict[str, Any], job_id:str, trace_id:str ) -> str:
        """
        Extract text from attachment.
        
        Args:
            attachment: Attachment data
            
        Returns:
            Attachment text
        """
        # This is a placeholder. In a real implementation, you would
        # extract text from the attachment based on its content type.
        # For now, we'll just return a message.
        return f"This is the content of attachment {attachment['filename']} ({attachment['content_type']})."
        
    def _determine_source_category(self, email_data: Dict[str, Any]) -> str:
        """
        Determine if an email is internal or external.
        
        Args:
            email_data: Email data
            
        Returns:
            'Internal' or 'External'
        """
        # Get company domain from config or use a default
        company_domains = config.get("app", {}).get("company_domains", [])
        if not company_domains:
            company_domains = ["company.com"]  # Default domain
            
        # Get sender email domain
        try:
            from_field = None
            if 'from' in email_data:
                from_field = email_data['from']
            elif 'from_' in email_data:
                from_field = email_data['from_']
                
            if from_field and 'email' in from_field:
                sender_domain = from_field['email'].split('@')[-1].lower()
                
                # Check if sender domain is a company domain
                if sender_domain in company_domains:
                    return "Internal"
        except Exception as e:
            job_id = email_data.get("job_id", "unknown")
            trace_id = email_data.get("trace_id", "unknown")
            logger.error(f"Error determining source category: {str(e)}, job_id: {job_id}, trace_id: {trace_id}")
                
        return "External"
        
 
        """
        Determine if the email requires a response.
        
        Args:
            email_analysis: Analysis results
            
        Returns:
            True if response is required, False otherwise
        """
        try:
            # Check intent - requests usually need responses
            intent = email_analysis.get("intent", "information_sharing").lower()
            if "request" in intent or "question" in intent or "follow_up" in intent:
                return True
                
            # Check if there are action items
            action_items = email_analysis.get("action_items", [])
            if action_items and len(action_items) > 0:
                return True
                
            # Check importance - important emails often need responses
            importance_score = email_analysis.get("importance_score", 0.5)
            if importance_score > 0.7:
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error determining if response required: {str(e)}")
            return False  # Default to not requiring response in case of error
        
    def _format_action_items(self, action_items: Any) -> List[Dict[str, Any]]:
        """
        Format action items to match the expected schema.
        
        Args:
            action_items: Action items from analysis result, could be a list of strings or already formatted
            
        Returns:
            List of action item dictionaries
        """
        try:
            # If action_items is already a list of dictionaries, return it
            if isinstance(action_items, list) and all(isinstance(item, dict) for item in action_items):
                return action_items
                
            # If action_items is a list of strings, convert to dictionaries
            if isinstance(action_items, list):
                formatted_action_items = []
                
                for item in action_items:
                    if isinstance(item, str):
                        formatted_action_items.append({
                            "description": item,
                            "status": "pending",
                            "priority": "medium"
                        })
                    elif isinstance(item, dict):
                        # If it's already a dict but might be missing required fields
                        action_item = {
                            "description": item.get("description", "Unknown action"),
                            "status": item.get("status", "pending"),
                            "priority": item.get("priority", "medium")
                        }
                        formatted_action_items.append(action_item)
                
                return formatted_action_items
                
            # If action_items is something else, return an empty list
            logger.warning(f"Unexpected action_items format: {type(action_items)}")
            return []
            
        except Exception as e:
            logger.error(f"Error formatting action items: {str(e)}")
            return []  # Return empty list in case of error
    
    def _format_entities(self, entities: Any) -> List[Dict[str, str]]:
        """
        Format entities to match the expected schema.
        
        Args:
            entities: Entities from analysis result, could be a list or dict
            
        Returns:
            List of entity dictionaries
        """
        try:
            # If entities is already a list, return it
            if isinstance(entities, list):
                return entities
                
            # If entities is a dictionary with categorized entities
            if isinstance(entities, dict):
                formatted_entities = []
                
                # Process people
                for person in entities.get("people", []):
                    formatted_entities.append({"name": person, "type": "person"})
                    
                # Process organizations
                for org in entities.get("organizations", []):
                    formatted_entities.append({"name": org, "type": "organization"})
                    
                # Process email addresses
                for email in entities.get("email_addresses", []):
                    formatted_entities.append({"name": email, "type": "email"})
                    
                # Process any other entity types
                for entity_type, entity_list in entities.items():
                    if entity_type not in ["people", "organizations", "email_addresses"] and isinstance(entity_list, list):
                        for entity in entity_list:
                            formatted_entities.append({"name": entity, "type": entity_type})
                
                return formatted_entities
                
            # If entities is something else, return an empty list
            logger.warning(f"Unexpected entities format: {type(entities)}")
            return []
            
        except Exception as e:
            logger.error(f"Error formatting entities: {str(e)}")
            return []  # Return empty list in case of error
    
    def _parse_job_id(self, job_id: Any) -> Any:
        """
        Parse job_id to ensure it's in the correct format.
        
        Args:
            job_id: Job ID from email data
            
        Returns:
            Parsed job ID
        """
        try:
            # If job_id is already a number, return it
            if isinstance(job_id, (int, float)):
                return job_id
                
            # If job_id is a string, try to convert it to a number
            if isinstance(job_id, str):
                # Try to convert to int first
                try:
                    return int(job_id)
                except ValueError:
                    # If that fails, try to convert to float
                    try:
                        return float(job_id)
                    except ValueError:
                        # If that also fails, return the original string
                        return job_id
            
            # If job_id is something else, return it as is
            return job_id
            
        except Exception as e:
            logger.error(f"Error parsing job_id: {str(e)}")
            return job_id  # Return original job_id in case of error
    
    def _determine_departments(self, email_data: Dict[str, Any], email_analysis: Dict[str, Any]) -> List[str]:
        """
        Determine relevant departments based on email content.
        
        Args:
            email_data: Email data
            email_analysis: Analysis results
            
        Returns:
            List of relevant department names
        """
        try:
            # Extract topics from analysis
            topics = email_analysis.get("topics", [])
            
            # Get department keywords from config
            department_keywords = config.get("email_analysis", {}).get("department_keywords", {})
            
            # If department keywords are not configured, use default empty dict
            if not department_keywords:
                logger.warning("Department keywords not found in config, using empty dictionary")
                department_keywords = {}
            
            # Map topics to departments
            relevant_departments = set()
            
            # Check topics against department keywords
            for topic in topics:
                topic_lower = topic.lower()
                for dept, keywords in department_keywords.items():
                    if any(keyword in topic_lower for keyword in keywords):
                        relevant_departments.add(dept)
                        
            # Check subject against department keywords
            subject = email_data.get("subject", "").lower()
            for dept, keywords in department_keywords.items():
                if any(keyword in subject for keyword in keywords):
                    relevant_departments.add(dept)
                    
            # Default to "General" if no departments matched
            if not relevant_departments:
                return ["General"]
                
            return list(relevant_departments)
        except Exception as e:
            logger.error(f"Error determining departments: {str(e)}")
            return ["General"]  # Default to General in case of error


# Global OpenAI service instance - initialize based on mock mode setting
logger.info(f"OPENAI_MOCK_MODE: {os.environ.get('OPENAI_MOCK_MODE', 'false').lower()}")

if os.environ.get("OPENAI_MOCK_MODE", "false").lower() == "true":
    logger.info("Initializing in mock mode")
    openai_service = MockOpenAIService()
else:
    logger.info("Initializing in real API mode")
    openai_service = OpenAIService()
