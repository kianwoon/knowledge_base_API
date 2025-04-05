#!/usr/bin/env python3
"""
Main application module for the Mail Analysis API.
"""

import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from loguru import logger

from app.core.config import config
from app.core.redis import redis_client
from app.core.auth import rate_limit_middleware
from app.core.snowflake import generate_id
from app.api.endpoints import router


# Note: For FastAPI >= 0.95.0, the recommended approach is to use the lifespan context manager:
# 
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Log startup
    env = config.get("app", {}).get("env", "development")
    version = config.get("app", {}).get("version", "0.1.0")
    logger.info(
        f"Mail Analysis API started - Environment: {env}, Version: {version}"
    )

    # Startup: Connect to Redis
    await redis_client.connect_with_retry()  # Will retry indefinitely
    
    yield
    
    # Shutdown: Disconnect from Redis
    await redis_client.disconnect()
    
    # Log shutdown
    logger.info("Mail Analysis API shutdown")


# Create FastAPI application
app = FastAPI(
    title="Mail Analysis API",
    description="API for analyzing Outlook 365 emails and attachments. Authentication uses API keys via the X-API-Key header.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    swagger_ui_parameters={
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
        "syntaxHighlight.theme": "monokai",
        "withCredentials": False,
        "defaultModelsExpandDepth": 3,
        "defaultModelExpandDepth": 3,
        "defaultModelRendering": "model",
        "docExpansion": "list",
        "showExtensions": True
    },
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
app.middleware("http")(rate_limit_middleware)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Add security headers to all responses.
    
    Args:
        request: Request object
        call_next: Next middleware
        
    Returns:
        Response
    """
    response = await call_next(request)
    
    # Add security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    
    # More permissive CSP to allow Swagger UI to function correctly
    if request.url.path.startswith("/api/docs") or request.url.path.startswith("/api/redoc") or request.url.path.startswith("/api/openapi.json"):
        # More permissive for documentation pages
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' https://fastapi.tiangolo.com data:; font-src 'self' data:"
    else:
        # Stricter for API endpoints
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' https://cdn.jsdelivr.net; img-src 'self' https://fastapi.tiangolo.com data:"
    
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    return response


@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    """
    Add trace ID to all responses.
    
    Args:
        request: Request object
        call_next: Next middleware
        
    Returns:
        Response
    """
    # Generate trace ID using Snowflake ID
    trace_id = generate_id()
    
    # Add trace ID to request state
    request.state.trace_id = trace_id
    
    # Process request
    response = await call_next(request)
    
    # Add trace ID to response headers
    response.headers["X-Trace-ID"] = trace_id
    
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Log all requests.
    
    Args:
        request: Request object
        call_next: Next middleware
        
    Returns:
        Response
    """
    # Get trace ID
    trace_id = getattr(request.state, "trace_id", generate_id())
    
    # Log request with trace_id in the message
    logger.info(
        f"Request {request.method} {request.url.path} - TraceID: {trace_id}, ClientIP: {request.client.host}, UserAgent: {request.headers.get('User-Agent', 'unknown')}",
        extra={"trace_id": trace_id}
    )
    
    # Process request
    start_time = time.time()
    
    try:
        response = await call_next(request)
        
        # Calculate request duration
        duration = time.time() - start_time
        
        # Log response with trace_id in the message
        logger.info(
            f"Response {response.status_code} - TraceID: {trace_id}, Duration: {duration:.3f}s",
            extra={"trace_id": trace_id}
        )
        
        return response
    except Exception as e:
        # Calculate request duration
        duration = time.time() - start_time
        
        # Log error with trace_id in the message
        logger.error(
            f"Error processing request: {str(e)}, type: {type(e).__name__}, trace_id: {trace_id}, duration: {duration:.3f}s",
            extra={"trace_id": trace_id}
        )
        
        # Create error response
        error_response = JSONResponse(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_server_error",
                    "message": "An internal server error occurred",
                    "trace_id": trace_id
                }
            }
        )
        
        # Log response for the error case with trace_id in the message
        logger.info(
            f"Response {HTTP_500_INTERNAL_SERVER_ERROR} - TraceID: {trace_id}, Duration: {duration:.3f}s",
            extra={"trace_id": trace_id}
        )
        
        return error_response

# Include API router - Using default FastAPI docs
app.include_router(router)


if __name__ == "__main__":
    """Run the application."""
    import uvicorn
    
    # Get port from config or use default
    port = config.get("app", {}).get("port", 8000)
    
    # Run the application
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=config.get("app", {}).get("env") == "development"
    )
