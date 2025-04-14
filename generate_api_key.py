#!/usr/bin/env python3
"""
Script to generate an API key for testing or add an existing API key to Redis.
"""

import asyncio
import secrets
import json
from datetime import datetime, timedelta
import argparse
from typing import List, Dict, Any

from app.core.hybrid_cache import hybrid_cache


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
    
    # Store in cache with 1-year expiration
    await store_api_key(api_key, client_id, tier)
    
    return api_key


async def store_api_key(api_key: str, client_id: str, tier: str) -> bool:
    """
    Store an API key in the hybrid cache (Redis + PostgreSQL).
    
    Args:
        api_key: The API key to store
        client_id: Unique client identifier
        tier: Subscription tier (free, pro, enterprise, admin)
        
    Returns:
        True if successful, False otherwise
    """
    # Store with 1-year expiration
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
    
    # Connect to hybrid cache
    await hybrid_cache.connect()
    
    # Store API key (will be written to both Redis and PostgreSQL)
    await hybrid_cache.setex(
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
    
    # Disconnect from cache
    await hybrid_cache.disconnect()
    
    return True


async def list_api_keys(client_id: str = None) -> List[Dict[str, Any]]:
    """
    List all API keys in the cache.
    
    Args:
        client_id: Optional filter to list only keys for a specific client
        
    Returns:
        List of API key information dictionaries
    """
    # Connect to hybrid cache
    await hybrid_cache.connect()
    
    # Get all API keys (will check Redis first, then PostgreSQL)
    keys = await hybrid_cache.keys("api_keys:*")
    
    # Fetch all API key data
    api_keys_info = []
    for key in keys:
        # Handle both bytes and string keys
        key_str = key if isinstance(key, str) else key.decode()
        data = await hybrid_cache.get(key_str)
        
        if data:
            # Handle both bytes and string data
            if isinstance(data, bytes):
                data = data.decode()
                
            api_key = key_str.split(':')[1]  # Extract the actual API key
            key_data = json.loads(data)
            
            # Filter by client_id if specified
            if client_id and key_data.get("client_id") != client_id:
                continue
                
            # Add API key to the data
            key_data["api_key"] = api_key
            
            # Calculate days until expiration
            if "expires_at" in key_data:
                expires_at = datetime.fromisoformat(key_data["expires_at"].rstrip("Z"))
                days_left = (expires_at - datetime.utcnow()).days
                key_data["days_until_expiration"] = days_left
                
            api_keys_info.append(key_data)
    
    # Disconnect from cache
    await hybrid_cache.disconnect()
    
    return api_keys_info


async def print_api_keys_table(api_keys_info: List[Dict[str, Any]]) -> None:
    """
    Print API keys information in a table format.
    
    Args:
        api_keys_info: List of API key information dictionaries
    """
    if not api_keys_info:
        print("No API keys found.")
        return
    
    # Print header
    header = f"{'API Key'} {'Client ID':<20} {'Tier':<12} {'Days Left':<10} {'Permissions'}"
    print("\n" + "=" * 100)
    print(header)
    print("-" * 100)
    
    # Print data
    for info in api_keys_info:
        # Mask API key for security (show only first 10 and last 4 characters)
        api_key = info.get("api_key", "")
        client_id = info.get("client_id", "")
        tier = info.get("tier", "")
        days_left = info.get("days_until_expiration", "")
        permissions = ", ".join(info.get("permissions", []))
        
        print(f"{api_key:<40} {client_id:<20} {tier:<12} {days_left:<10} {permissions}")
    
    print("=" * 100 + "\n")


async def main():
    """Main function."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Generate an API key for testing or add an existing API key")
    parser.add_argument("--client-id", type=str, default="test_client", help="Client ID")
    parser.add_argument("--tier", type=str, default="free", choices=["free", "pro", "enterprise", "admin"], help="Subscription tier")
    parser.add_argument("--existing-key", type=str, help="Add an existing API key to Redis instead of generating a new one")
    parser.add_argument("--list", action="store_true", help="List all API keys in Redis")
    parser.add_argument("--list-client", type=str, help="List API keys for a specific client")
    args = parser.parse_args()
    
    if args.list or args.list_client:
        # List API keys
        client_filter = args.list_client if args.list_client else None
        api_keys_info = await list_api_keys(client_filter)
        await print_api_keys_table(api_keys_info)
    elif args.existing_key:
        # Store existing API key
        success = await store_api_key(args.existing_key, args.client_id, args.tier)
        if success:
            print(f"Added existing API key to Redis: {args.existing_key}")
            print(f"Client ID: {args.client_id}")
            print(f"Tier: {args.tier}")
        else:
            print("Failed to add API key to Redis")
    else:
        # Generate API key
        api_key = await generate_api_key(args.client_id, args.tier)
        
        # Print API key
        print(f"Generated API key: {api_key}")
        print(f"Client ID: {args.client_id}")
        print(f"Tier: {args.tier}")


if __name__ == "__main__":
    """Run the script."""
    asyncio.run(main())
