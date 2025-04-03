#!/usr/bin/env python3
"""
Script to generate an encryption key for testing.
"""

import base64
import os


def generate_encryption_key():
    """
    Generate a random encryption key.
    
    Returns:
        Base64-encoded encryption key
    """
    # Generate 32 random bytes
    key = os.urandom(32)
    
    # Encode as base64
    encoded_key = base64.b64encode(key).decode()
    
    return encoded_key


if __name__ == "__main__":
    """Run the script."""
    # Generate encryption key
    encryption_key = generate_encryption_key()
    
    # Print encryption key
    print(f"Generated encryption key: {encryption_key}")
    print("Add this to your .env file as ENCRYPTION_KEY=<key>")
