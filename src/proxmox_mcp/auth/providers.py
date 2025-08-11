"""
Authentication providers for ProxmoxMCP.

This module provides custom authentication providers that integrate with Django
and other authentication systems.
"""

import logging
from datetime import datetime
from typing import Optional, Set
from pydantic import AnyHttpUrl

try:
    import django
    from django.core.exceptions import ObjectDoesNotExist
    from asgiref.sync import sync_to_async
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False

from .models import ProxmoxMCPToken
from .utils import hash_sha512


logger = logging.getLogger("proxmox-mcp.auth")


class YartuMCPAuthProvider:
    """
    Django-based authentication provider for ProxmoxMCP.
    
    This provider integrates with Django's authentication system,
    supporting token-based authentication with RBAC.
    """
    
    required_scopes: Set[str] = set()
    issuer_url: AnyHttpUrl = AnyHttpUrl("https://localhost")
    service_documentation_url: Optional[str] = None
    client_registration_options = None
    revocation_options = None
    scheme: str = "https"
    
    def __init__(self, 
                 default_scopes: Optional[Set[str]] = None,
                 admin_scope: str = "admin",
                 user_scope: str = "user",
                 write_scope: str = "write"):
        """
        Initialize the authentication provider.
        
        Args:
            default_scopes: Default scopes for authenticated users
            admin_scope: Scope name for admin users
            user_scope: Scope name for regular users  
            write_scope: Scope name for write permissions
        """
        self.default_scopes = default_scopes or {"user"}
        self.admin_scope = admin_scope
        self.user_scope = user_scope
        self.write_scope = write_scope
        
        if not DJANGO_AVAILABLE:
            logger.warning("Django is not available. Authentication will be disabled.")

    async def load_access_token(self, token: str) -> Optional[ProxmoxMCPToken]:
        """
        Load and validate an access token.
        
        Args:
            token: Raw token string
            
        Returns:
            ProxmoxMCPToken if valid, None otherwise
        """
        if not DJANGO_AVAILABLE:
            logger.error("Django is not available for authentication")
            return None
            
        try:
            # Import here to avoid import errors when Django is not configured
            from auth.models import ApplicationToken
            
            # Hash the token and look it up in the database
            token_hash = hash_sha512(token)
            
            app_token = await sync_to_async(
                ApplicationToken.objects.select_related('user').select_related('user__role').get
            )(token_hash=token_hash)
            
            # Check if token is expired
            if app_token.expires and app_token.expires <= datetime.now():
                logger.warning(f"Expired token used by user {app_token.user.username}")
                return None
                
            # Determine scopes based on user role
            scopes = {self.user_scope}
            
            if hasattr(app_token.user, 'role') and app_token.user.role:
                if app_token.user.role.is_superuser:
                    scopes.add(self.admin_scope)
                    scopes.add(self.write_scope)
                elif hasattr(app_token.user.role, 'can_write') and app_token.user.role.can_write:
                    scopes.add(self.write_scope)
            elif app_token.user.is_superuser:
                scopes.update({self.admin_scope, self.write_scope})
            
            # Create and return the token
            return ProxmoxMCPToken(
                client_id="proxmox-mcp",
                user_id=app_token.user.id,
                username=app_token.user.username,
                permission=app_token.permission,
                expires_at=app_token.expires.timestamp() if app_token.expires else (datetime.now().timestamp() + 86400),
                scopes=scopes,
                token_hash=token_hash,
                is_superuser=getattr(app_token.user, 'is_superuser', False)
            )
            
        except ObjectDoesNotExist:
            logger.warning(f"Invalid token attempted")
            return None
        except Exception as e:
            logger.error(f"Error loading access token: {e}")
            return None

    def get_required_scopes(self, tool_name: str) -> Set[str]:
        """
        Get required scopes for a specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Set of required scopes
        """
        # Define tool-specific scope requirements
        admin_tools = {
            "delete_vm", "create_vm", "reset_vm", 
            "stop_vm", "shutdown_vm"
        }
        
        write_tools = {
            "start_vm", "execute_vm_command", 
            "create_snapshot", "rollback_snapshot"
        }
        
        if tool_name in admin_tools:
            return {self.admin_scope}
        elif tool_name in write_tools:
            return {self.write_scope}
        else:
            # Read-only tools only require user scope
            return {self.user_scope}


class SimpleTokenAuthProvider:
    """
    Simple token-based authentication provider for testing and development.
    
    This provider uses a simple token validation without Django dependency.
    """
    
    required_scopes: Set[str] = set()
    issuer_url: AnyHttpUrl = AnyHttpUrl("https://localhost")
    service_documentation_url: Optional[str] = None
    client_registration_options = None
    revocation_options = None
    scheme: str = "https"
    
    def __init__(self, valid_tokens: Optional[dict] = None):
        """
        Initialize with a dictionary of valid tokens.
        
        Args:
            valid_tokens: Dict mapping token -> {"scopes": set, "user": str}
        """
        self.valid_tokens = valid_tokens or {
            "admin-token": {"scopes": {"admin", "write", "user"}, "user": "admin"},
            "user-token": {"scopes": {"user"}, "user": "user"},
            "write-token": {"scopes": {"write", "user"}, "user": "writer"}
        }
    
    async def load_access_token(self, token: str) -> Optional[ProxmoxMCPToken]:
        """
        Load access token from simple token store.
        
        Args:
            token: Raw token string
            
        Returns:
            ProxmoxMCPToken if valid, None otherwise
        """
        if token not in self.valid_tokens:
            return None
            
        token_data = self.valid_tokens[token]
        
        return ProxmoxMCPToken(
            client_id="proxmox-mcp-simple",
            username=token_data["user"],
            permission="read",
            expires_at=datetime.now().timestamp() + 86400,  # 24 hours
            scopes=token_data["scopes"],
            is_superuser="admin" in token_data["scopes"]
        )
