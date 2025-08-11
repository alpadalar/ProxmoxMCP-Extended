"""
Authentication utilities for ProxmoxMCP.

This module provides hashing, token validation, and other auth-related utilities.
"""

import hashlib
import secrets
from typing import Optional


def hash_sha512(value: str) -> str:
    """
    Generate SHA-512 hash of a string value.
    
    Args:
        value: String to hash
        
    Returns:
        Hexadecimal SHA-512 hash
    """
    return hashlib.sha512(value.encode('utf-8')).hexdigest()


def generate_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token.
    
    Args:
        length: Length of the token in bytes
        
    Returns:
        Hex-encoded random token
    """
    return secrets.token_hex(length)


def validate_token_format(token: str) -> bool:
    """
    Validate token format (basic checks).
    
    Args:
        token: Token string to validate
        
    Returns:
        True if format is valid, False otherwise
    """
    if not token or not isinstance(token, str):
        return False
        
    # Basic length check (adjust according to your token format)
    if len(token) < 16 or len(token) > 128:
        return False
        
    # Check if token contains only valid characters (hex, alphanumeric, etc.)
    try:
        # Allow hex tokens
        int(token, 16)
        return True
    except ValueError:
        # Allow alphanumeric tokens
        return token.replace('-', '').replace('_', '').isalnum()


def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    """
    Extract bearer token from Authorization header.
    
    Args:
        authorization_header: HTTP Authorization header value
        
    Returns:
        Token string if found, None otherwise
    """
    if not authorization_header:
        return None
        
    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None
        
    return parts[1]
