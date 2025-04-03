#!/usr/bin/env python3
"""
Script to generate an API key for testing.
"""

import asyncio
import secrets
import json
from datetime import datetime, timedelta
import argparse

from app.core.redis import redis_client


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
    
    # Get permissions for tier
    permissions = []
    if tier == "free":
        permissions = ["analyze", "status", "results"]
    elif tier == "pro":
        permissions = ["analyze", "status", "results", "webhook", "priority"]
    elif tier == "enterprise":
        permissions = ["analyze", "status", "results", "webhook", "priority", "custom_models", "batch"]
    elif tier == "admin":
        permissions = ["analyze", "status", "results", "webhook", "priority", "custom_models", "batch", "admin"]
    
    # Connect to Redis
    await redis_client.connect()
    
    # Store API key
    await redis_client.setex(
        f"api_keys:{api_key}",
        60 * 60 * 24 * 365,  # 1 year in seconds
        json.dumps({
            "client_id": client_id,
            "tier": tier,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "expires_at": expiration.isoformat() + "Z",
            "rate_limit_override": None,
            "permissions": permissions
        })
    )
    
    # Disconnect from Redis
    await redis_client.disconnect()
    
    return api_key


async def main():
    """Main function."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Generate an API key for testing")
    parser.add_argument("--client-id", type=str, default="test_client", help="Client ID")
    parser.add_argument("--tier", type=str, default="free", choices=["free", "pro", "enterprise", "admin"], help="Subscription tier")
    args = parser.parse_args()
    
    # Generate API key
    api_key = await generate_api_key(args.client_id, args.tier)
    
    # Print API key
    print(f"Generated API key: {api_key}")
    print(f"Client ID: {args.client_id}")
    print(f"Tier: {args.tier}")


if __name__ == "__main__":
    """Run the script."""
    asyncio.run(main())
