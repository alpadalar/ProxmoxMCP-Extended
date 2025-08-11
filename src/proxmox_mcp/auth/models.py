"""
Authentication models for ProxmoxMCP Django integration.

This module provides token-based authentication models compatible with Django.
"""

from datetime import datetime, timedelta
from typing import Set, Optional, Any, Dict
from pydantic import BaseModel


class ProxmoxMCPToken(BaseModel):
    """
    Token model for ProxmoxMCP authentication.
    
    Compatible with FastMCP authentication requirements while
    integrating with Django User and Role models.
    """
    client_id: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    permission: Optional[str] = None
    expires_at: float
    scopes: Set[str]
    
    # Additional metadata
    token_hash: Optional[str] = None
    is_superuser: bool = False
    
    @classmethod
    def from_django_user(cls, user: Any, permission: str = "read", expires_days: int = 1) -> "ProxmoxMCPToken":
        """
        Create a ProxmoxMCPToken from a Django User object.
        
        Args:
            user: Django User instance
            permission: Permission level (read, write, admin)
            expires_days: Token expiration in days
            
        Returns:
            ProxmoxMCPToken instance
        """
        # Determine scopes based on user role
        scopes = {"user"}
        
        if hasattr(user, 'role') and user.role:
            if user.role.is_superuser:
                scopes.add("admin")
                scopes.add("write")
            elif hasattr(user.role, 'can_write') and user.role.can_write:
                scopes.add("write")
        elif user.is_superuser:
            scopes.update({"admin", "write"})
            
        return cls(
            client_id="proxmox-mcp",
            user_id=user.id,
            username=user.username,
            permission=permission,
            expires_at=(datetime.now() + timedelta(days=expires_days)).timestamp(),
            scopes=scopes,
            is_superuser=getattr(user, 'is_superuser', False)
        )
    
    def has_scope(self, scope: str) -> bool:
        """Check if token has a specific scope."""
        return scope in self.scopes
    
    def has_any_scope(self, scopes: Set[str]) -> bool:
        """Check if token has any of the specified scopes."""
        return bool(self.scopes & scopes)
    
    def has_all_scopes(self, scopes: Set[str]) -> bool:
        """Check if token has all of the specified scopes."""
        return scopes.issubset(self.scopes)
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.now().timestamp() > self.expires_at


class ApplicationToken(BaseModel):
    """
    Django ApplicationToken model representation.
    
    This model should match your Django ApplicationToken model structure.
    """
    id: int
    token_hash: str
    user_id: int
    permission: str
    expires: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
