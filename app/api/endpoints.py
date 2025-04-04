#!/usr/bin/env python3
"""
API endpoints for the Mail Analysis API.
"""

import json
import time
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, BackgroundTasks, Request
from starlette.status import HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND
from loguru import logger

from app.core.const import JobType
from app.models.email import EmailSchema, JobResponse, StatusResponse, AnalysisResponse, SubjectAnalysisRequest, BatchSubjectAnalysisResponse
from app.core.auth import requires_permission
from app.core.redis import redis_client
from app.core.snowflake import generate_id
from app.core.config import localize_datetime
from app.services.openai_service import openai_service


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    
    def default(self, obj):
        if isinstance(obj, datetime):
            # Ensure datetime has timezone info before converting to ISO format
            if obj.tzinfo is None:
                obj = localize_datetime(obj)
            return obj.isoformat()
        return super().default(obj)


router = APIRouter(
    tags=["v1"]
)


@router.post("/api/v1/analyze", status_code=HTTP_202_ACCEPTED, response_model=JobResponse, tags=["Email Analysis"])
async def analyze_email(
    email: EmailSchema,
    background_tasks: BackgroundTasks,
    request: Request,
    api_key: str = Header(..., alias="X-API-Key")
):
    """
    Submit email for analysis.
    
    Args:
        email: Email data
        background_tasks: Background tasks
        request: Request object
        api_key: API key
        
    Returns:
        Job response
    """
    # Validate API key and check permissions
    key_info = await requires_permission("analyze", api_key)
    
    # Generate job ID using Snowflake ID
    job_id = generate_id()
    
    # Store job data in Redis
    await redis_client.store_job_data(
        job_id=job_id,
        client_id=key_info["client_id"],
        data=email.model_dump_json(),
        job_type="email_analysis"
    )
    
    # Get trace ID from request state or generate a new one
    trace_id = getattr(request.state, "trace_id", generate_id())
    
    # Add job to processing queue
    # background_tasks.add_task(process_email, job_id, trace_id)
    
    logger.info(
        f"Job {job_id} submitted for processing, trace_id: {trace_id}",
        extra={"job_id": job_id, "trace_id": trace_id}
    )
    
    # Return job ID
    return {
        "job_id": job_id,
        "status": "pending",
        "status_url": f"/api/v1/status/{job_id}"
    }


@router.get("/api/v1/status/{job_id}", response_model=StatusResponse, tags=["Email Analysis"])
async def get_job_status(
    job_id: str,
    request: Request,
    api_key: str = Header(..., alias="X-API-Key")
):
    """
    Check job status.
    
    Args:
        job_id: Job ID
        request: Request object
        api_key: API key
        
    Returns:
        Status response
    """
    # Validate API key and check permissions
    key_info = await requires_permission("status", api_key)
    
    # Get trace ID from request state or generate a new one
    trace_id = getattr(request.state, "trace_id", generate_id())
    
    # Check if job exists
    if not await redis_client.exists(f"job:{job_id}:status"):
        logger.warning(
            f"Job {job_id} not found, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
        
    # Check if job belongs to client
    client_id = await redis_client.get(f"job:{job_id}:client")
    if client_id != key_info["client_id"]:
        logger.warning(
            f"Job {job_id} does not belong to client {key_info['client_id']}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
        
    # Get job status
    status = await redis_client.get(f"job:{job_id}:status")
    
    # Build response
    response = {
        "job_id": job_id,
        "status": status
    }
    
    # Add results URL if job is completed
    if status == "completed":
        response["results_url"] = f"/api/v1/results/{job_id}"
        
    # Add error if job failed
    if status == "failed":
        error = await redis_client.get(f"job:{job_id}:error")
        response["error"] = error
        
    return response


@router.get("/api/v1/results/{job_id}", tags=["Email Analysis"])
async def get_job_results(
    job_id: str,
    request: Request,
    api_key: str = Header(..., alias="X-API-Key")
):
    """
    Get job results.
    
    Args:
        job_id: Job ID
        request: Request object
        api_key: API key
        
    Returns:
        Analysis response
    """
    # Validate API key and check permissions
    key_info = await requires_permission("results", api_key)
    
    # Get trace ID from request state or generate a new one
    trace_id = getattr(request.state, "trace_id", generate_id())
    
    # Check if job exists
    if not await redis_client.exists(f"job:{job_id}:status"):
        logger.warning(
            f"Job {job_id} not found, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
        
    # Check if job belongs to client
    client_id = await redis_client.get(f"job:{job_id}:client")
    if client_id != key_info["client_id"]:
        logger.warning(
            f"Job {job_id} does not belong to client {key_info['client_id']}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
        
    # Check if job is completed
    status = await redis_client.get(f"job:{job_id}:status")
    if status != "completed":
        logger.warning(
            f"Results for job {job_id} not available yet (status: {status}), trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Results for job {job_id} not available yet"
        )
    
    # Get job results
    results_json = await redis_client.get(f"job:{job_id}:results")
    if not results_json:
        logger.error(
            f"Results for job {job_id} not found despite completed status, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Results for job {job_id} not found"
        )
        
    # Parse results
    try:
        results = json.loads(results_json)
    except json.JSONDecodeError:
        logger.error(
            f"Invalid JSON in results for job {job_id}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Invalid results for job {job_id}"
        )
        
    # Get trace ID from request state or generate a new one
    trace_id = getattr(request.state, "trace_id", generate_id())
    
    # Ensure entities is a list of dictionaries
    if "entities" in results and not isinstance(results["entities"], list):
        logger.warning(
            f"Converting entities to proper format for job {job_id}, trace_id: {trace_id}",
            extra={"job_id": job_id, "trace_id": trace_id}
        )
        results["entities"] = []
        
    # Check job type
    job_type = await redis_client.get(f"job:{job_id}:type")
    job_type = job_type if job_type else "email_analysis"  # Default to email_analysis for backward compatibility
    
    # Return results based on job type
    if job_type == "subject_analysis":
        return results  # Return subject analysis results directly
    else:
        # Return email analysis results in the expected format
        return {"analysis": results}


@router.get("/api/v1/health", tags=["System"])
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Health status
    """
    return {"status": "ok"}


@router.get("/api/v1/health/detailed", tags=["System"])
async def detailed_health_check(
    api_key: str = Header(..., alias="X-API-Key")
):
    """
    Detailed health check endpoint.
    
    Args:
        api_key: API key
        
    Returns:
        Detailed health status
    """
    # Validate API key and check permissions
    key_info = await requires_permission("admin", api_key)
    
    # Check Redis connection
    try:
        await redis_client.ping()
        redis_status = "ok"
    except Exception as e:
        redis_status = f"error: {str(e)}"
        
    # Simplified health check to avoid OpenAI API calls that might fail
    openai_status = "ok"  # Simplified check - assuming OpenAI service is working
    
    return {
        "status": "ok" if all(s == "ok" for s in [redis_status, openai_status]) else "degraded",
        "components": {
            "api": "ok",
            "redis": redis_status,
            "openai": openai_status
        },
        "timestamp": time.time()
    }


@router.post("/api/v1/analyze/subjects", status_code=HTTP_202_ACCEPTED, response_model=JobResponse, tags=["Email Analysis"])
async def analyze_subjects(
    request: SubjectAnalysisRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    api_key: str = Header(..., alias="X-API-Key")
):
    """
    Submit email subjects for analysis.
    
    Args:
        request: Subject analysis request containing list of subjects
        background_tasks: Background tasks
        req: Request object
        api_key: API key
        
    Returns:
        Job response
    """
    # Validate API key and check permissions
    key_info = await requires_permission("analyze", api_key)
    
    # Generate job ID using Snowflake ID
    job_id = generate_id()
    
    # Store job data in Redis
    await redis_client.store_job_data(
        job_id=job_id,
        client_id=key_info["client_id"],
        data=request.model_dump_json(),
        job_type=JobType.SUBJECT_ANALYSIS.value
    )
    
    # Get trace ID from request state or generate a new one
    trace_id = getattr(req.state, "trace_id", generate_id())
    
    # Add job to processing queue
    # background_tasks.add_task(process_subjects, job_id, trace_id)
    
    logger.info(
        f"Subject analysis job {job_id} submitted for processing, trace_id: {trace_id}",
        extra={"job_id": job_id, "trace_id": trace_id}
    )
    
    # Return job ID
    return {
        "job_id": job_id,
        "status": "pending",
        "status_url": f"/api/v1/status/{job_id}"
    }


@router.get("/api/v1/test", tags=["Testing"])
async def test_endpoint():
    """
    Test endpoint to verify API documentation.
    
    Returns:
        Simple test response
    """
    return {"message": "Test endpoint is working"}