#!/usr/bin/env python3
"""
Authentication module for the Mail Analysis API.
"""

import time
import json
import secrets
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import uuid
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN, HTTP_429_TOO_MANY_REQUESTS
from loguru import logger

from app.core.config import config


# API key header - Use custom APIKeyHeader for API key authentication only
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_redis_client():
    """
    Get Redis client.
    
    Returns:
        Redis client
    """
    # This is a placeholder. In a real implementation, you would
    # return an actual Redis client instance.
    from app.core.redis import redis_client
    return redis_client


async def generate_api_key(client_id: str, tier: str) -> str:
    """
    Generate a new API key.
    
    Args:
        client_id: Unique client identifier
        tier: Subscription tier (free, pro, enterprise)
        
    Returns:
        Newly generated API key
    """
    random_part = secrets.token_hex(16)
    api_key = f"ma_{tier}_{random_part}"
    
    # Store in Redis with 1-year expiration
    expiration = datetime.utcnow() + timedelta(days=365)
    
    redis_client = await get_redis_client()
    await redis_client.setex(
        f"api_keys:{api_key}",
        60 * 60 * 24 * 365,  # 1 year in seconds
        json.dumps({
            "client_id": client_id,
            "tier": tier,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "expires_at": expiration.isoformat() + "Z",
            "rate_limit_override": None,
            "permissions": await get_tier_permissions(tier)
        })
    )
    
    logger.info(f"Generated API key for client {client_id} with tier {tier}")
    
    return api_key


async def get_tier_permissions(tier: str) -> List[str]:
    """
    Get permissions for a subscription tier.
    
    Args:
        tier: Subscription tier
        
    Returns:
        List of permission strings
    """
    base_permissions = ["analyze", "status", "results"]
    
    if tier == "free":
        return base_permissions
    elif tier == "pro":
        return base_permissions + ["webhook", "priority"]
    elif tier == "enterprise":
        return base_permissions + ["webhook", "priority", "custom_models", "batch"]
    else:
        return []


async def validate_api_key(api_key: str) -> Dict:
    """
    Validate an API key.
    
    Args:
        api_key: API key to validate
        
    Returns:
        API key metadata if valid
        
    Raises:
        HTTPException: If API key is invalid or expired
    """
    if not api_key:
        logger.warning("Missing API key")
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="API key is required"
        )
    
    redis_client = await get_redis_client()
    key_data = await redis_client.get(f"api_keys:{api_key}")
    
    if not key_data:
        logger.warning(f"Invalid API key: {api_key[:8]}...")
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
        
    try:
        key_info = json.loads(key_data)
    except json.JSONDecodeError:
        logger.error(f"Invalid API key data format: {key_data}")
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid API key data"
        )
    
    # Check if key has expired
    expires_at = datetime.fromisoformat(key_info["expires_at"].rstrip("Z"))
    if expires_at < datetime.utcnow():
        logger.warning(f"Expired API key: {api_key[:8]}...")
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Expired API key"
        )
        
    return key_info


async def check_rate_limit(api_key: str, key_info: Dict) -> bool:
    """
    Check if request is within rate limits.
    
    Args:
        api_key: API key
        key_info: API key metadata
        
    Returns:
        True if within limits, False otherwise
    """
    tier = key_info["tier"]
    client_id = key_info["client_id"]
    
    # Get rate limit for tier
    rate_limit_config = config.get("rate_limits", {}).get("tiers", {}).get(tier, {})
    rate_limit = key_info.get("rate_limit_override") or rate_limit_config.get("requests_per_minute", 10)
    
    # Current timestamp
    now = int(time.time())
    window_start = now - 60  # 1 minute window
    
    # Redis key for rate limiting
    rate_key = f"rate_limit:{client_id}:{now // 60}"
    
    redis_client = await get_redis_client()
    
    # Execute commands individually to avoid pipeline issues with async Redis
    await redis_client.zadd(rate_key, {str(now): now})
    await redis_client.zremrangebyscore(rate_key, 0, window_start)
    request_count = await redis_client.zcard(rate_key)
    await redis_client.expire(rate_key, 120)
    
    return int(request_count) <= int(rate_limit)


async def get_current_usage(client_id: str) -> Tuple[int, int]:
    """
    Get current API usage.
    
    Args:
        client_id: Client ID
        
    Returns:
        Tuple of (current usage, reset time)
    """
    now = int(time.time())
    rate_key = f"rate_limit:{client_id}:{now // 60}"
    
    redis_client = await get_redis_client()
    request_count = await redis_client.zcard(rate_key)
    
    # Reset time is the start of the next minute
    reset_time = (now // 60 + 1) * 60
    
    return request_count, reset_time


async def requires_permission(permission: str, api_key: str = Depends(api_key_header)):
    """
    Dependency for requiring a specific permission.
    
    Args:
        permission: Required permission string
        api_key: API key
        
    Returns:
        API key metadata
    """
    key_info = await validate_api_key(api_key)
    
    if permission not in key_info["permissions"]:
        logger.warning(f"Permission denied: {permission} for API key {api_key[:8]}...")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=f"This operation requires the '{permission}' permission"
        )
    
    return key_info


async def rate_limit_middleware(request: Request, call_next):
    """
    Middleware for rate limiting.
    
    Args:
        request: Request object
        call_next: Next middleware
        
    Returns:
        Response
    """
    # Get API key from request
    api_key = request.headers.get("X-API-Key")
    
    if api_key:
        try:
            # Validate API key
            key_info = await validate_api_key(api_key)
            
            # Check rate limit
            if not await check_rate_limit(api_key, key_info):
                # Get current usage and reset time
                client_id = key_info["client_id"]
                request_count, reset_time = await get_current_usage(client_id)
                
                # Get rate limit for tier
                tier = key_info["tier"]
                rate_limit_config = config.get("rate_limits", {}).get("tiers", {}).get(tier, {})
                rate_limit = key_info.get("rate_limit_override") or rate_limit_config.get("requests_per_minute", 10)
                
                logger.warning(f"Rate limit exceeded for client {client_id}: {request_count}/{rate_limit}")
                
                # Return rate limit error
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "code": "rate_limit_exceeded",
                            "message": f"You have exceeded your rate limit of {rate_limit} requests per minute",
                            "details": {
                                "limit": rate_limit,
                                "period": "minute",
                                "reset_at": datetime.fromtimestamp(reset_time).isoformat() + "Z"
                            },
                            "request_id": str(uuid.uuid4())
                        }
                    },
                    headers={
                        "X-RateLimit-Limit": str(rate_limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_time)
                    }
                )
        except HTTPException:
            # Pass through authentication errors
            pass
    
    # Process request normally
    response = await call_next(request)
    
    # Add rate limit headers if API key is valid
    if api_key:
        try:
            key_info = await validate_api_key(api_key)
            tier = key_info["tier"]
            client_id = key_info["client_id"]
            
            # Get rate limit info
            rate_limit_config = config.get("rate_limits", {}).get("tiers", {}).get(tier, {})
            rate_limit = key_info.get("rate_limit_override") or rate_limit_config.get("requests_per_minute", 10)
            
            # Get current usage
            request_count, reset_time = await get_current_usage(client_id)
            
            # Add headers
            response.headers["X-RateLimit-Limit"] = str(rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, rate_limit - request_count))
            response.headers["X-RateLimit-Reset"] = str(reset_time)
        except Exception:
            # Ignore errors in rate limit header generation
            pass
    
    return response


async def log_failed_auth(api_key: str, client_ip: str):
    """
    Log failed authentication attempt.
    
    Args:
        api_key: Attempted API key
        client_ip: Client IP address
    """
    # Log the event
    logger.warning(
        "Failed authentication attempt",
        extra={
            "api_key": mask_api_key(api_key),
            "client_ip": client_ip
        }
    )
    
    # Increment counter in Redis
    redis_client = await get_redis_client()
    key = f"failed_auth:{client_ip}"
    count = await redis_client.incr(key)
    await redis_client.expire(key, 3600)  # 1 hour expiry
    
    # Check for potential brute force attack
    if count >= 10:
        logger.critical(
            "Potential brute force attack detected",
            extra={
                "client_ip": client_ip,
                "attempt_count": count
            }
        )
        
        # Implement temporary IP ban
        await redis_client.setex(f"ip_banned:{client_ip}", 3600, "1")


def mask_api_key(api_key: str) -> str:
    """
    Mask API key for logging.
    
    Args:
        api_key: API key
        
    Returns:
        Masked API key
    """
    if not api_key or api_key == "none":
        return "none"
    
    parts = api_key.split("_")
    if len(parts) >= 3:
        return f"{parts[0]}_{parts[1]}_{parts[2][:4]}{'*' * (len(parts[2]) - 4)}"
    return f"{api_key[:4]}{'*' * (len(api_key) - 4)}"
