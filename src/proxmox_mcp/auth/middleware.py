"""
Authentication and authorization middleware for ProxmoxMCP.

This module provides RBAC (Role-Based Access Control) middleware
for controlling access to MCP tools based on user scopes.
"""

import logging
from typing import List, Set, Optional

try:
    from fastmcp import FastMCP
    FASTMCP_AVAILABLE = True
    # Try to import middleware components
    try:
        from fastmcp.server.middleware import Middleware, MiddlewareContext
        from fastmcp.server.dependencies import get_access_token
        from fastmcp.exceptions import ToolError
    except ImportError:
        # Alternative import paths
        try:
            from fastmcp.middleware import Middleware, MiddlewareContext
            from fastmcp.dependencies import get_access_token
            from fastmcp.exceptions import ToolError
        except ImportError:
            FASTMCP_AVAILABLE = False
except ImportError:
    FASTMCP_AVAILABLE = False

from .models import ProxmoxMCPToken


logger = logging.getLogger("proxmox-mcp.auth.middleware")


class ScopeRBAC(Middleware):
    """
    Role-Based Access Control middleware using scopes.
    
    This middleware filters available tools and validates permissions
    based on user scopes defined in the authentication token.
    """
    
    def __init__(self, 
                 tool_scope_mapping: Optional[dict] = None,
                 default_scope: str = "user",
                 admin_scope: str = "admin",
                 write_scope: str = "write"):
        """
        Initialize RBAC middleware.
        
        Args:
            tool_scope_mapping: Dict mapping tool names to required scopes
            default_scope: Default scope for tools without specific requirements
            admin_scope: Scope name for admin operations
            write_scope: Scope name for write operations
        """
        self.tool_scope_mapping = tool_scope_mapping or self._get_default_tool_scope_mapping()
        self.default_scope = default_scope
        self.admin_scope = admin_scope
        self.write_scope = write_scope
        
        if not FASTMCP_AVAILABLE:
            logger.error("FastMCP is not available. RBAC middleware will be disabled.")

    def _get_default_tool_scope_mapping(self) -> dict:
        """
        Get default tool-to-scope mapping for ProxmoxMCP tools.
        
        Returns:
            Dictionary mapping tool names to required scopes
        """
        return {
            # Admin-only operations (destructive or sensitive)
            "delete_vm": {"admin"},
            "create_vm": {"admin"}, 
            "reset_vm": {"admin"},
            "stop_vm": {"admin"},
            "shutdown_vm": {"write"},
            
            # Write operations  
            "start_vm": {"write"},
            "execute_vm_command": {"write"},
            "create_snapshot": {"write"},
            "rollback_snapshot": {"write"},
            
            # Read-only operations (available to all authenticated users)
            "get_nodes": {"user"},
            "get_node_status": {"user"},
            "get_vms": {"user"},
            "get_containers": {"user"},
            "get_storage": {"user"},
            "get_cluster_status": {"user"},
            "get_vm_usage": {"user"},
            "health": {"user"},
        }

    def _get_tool_required_scopes(self, tool_name: str, tool_tags: Optional[List[str]] = None) -> Set[str]:
        """
        Get required scopes for a tool.
        
        Args:
            tool_name: Name of the tool
            tool_tags: Tool tags (if available)
            
        Returns:
            Set of required scopes
        """
        # Use tags if available (highest priority)
        if tool_tags:
            return set(tool_tags)
            
        # Use explicit mapping
        if tool_name in self.tool_scope_mapping:
            return self.tool_scope_mapping[tool_name]
            
        # Default to user scope
        return {self.default_scope}

    async def on_list_tools(self, ctx: MiddlewareContext, call_next):
        """
        Filter tools based on user scopes.
        
        Args:
            ctx: Middleware context
            call_next: Next middleware/handler in chain
            
        Returns:
            Filtered list of tools the user can access
        """
        if not FASTMCP_AVAILABLE:
            return await call_next(ctx)
            
        try:
            token = get_access_token()
            if not token or not isinstance(token, ProxmoxMCPToken):
                logger.warning("No valid token found for tool listing")
                return []
                
            # Get all available tools
            tools = await call_next(ctx)
            
            # Filter tools based on user scopes
            allowed_tools = []
            for tool in tools:
                required_scopes = self._get_tool_required_scopes(
                    tool.name, 
                    getattr(tool, 'tags', None)
                )
                
                # Check if user has any of the required scopes
                if not required_scopes or token.has_any_scope(required_scopes):
                    allowed_tools.append(tool)
                else:
                    logger.debug(f"Tool '{tool.name}' filtered out for user {token.username} "
                               f"(required: {required_scopes}, has: {token.scopes})")
            
            logger.info(f"User {token.username} has access to {len(allowed_tools)}/{len(tools)} tools")
            return allowed_tools
            
        except Exception as e:
            logger.error(f"Error in tool filtering: {e}")
            # In case of error, return empty list for security
            return []

    async def on_call_tool(self, ctx: MiddlewareContext, call_next):
        """
        Validate tool access before execution.
        
        Args:
            ctx: Middleware context
            call_next: Next middleware/handler in chain
            
        Returns:
            Tool execution result
            
        Raises:
            ToolError: If user lacks required permissions
        """
        if not FASTMCP_AVAILABLE:
            return await call_next(ctx)
            
        try:
            token = get_access_token()
            if not token or not isinstance(token, ProxmoxMCPToken):
                raise ToolError("Kimlik doğrulama gerekli. Geçerli bir token sağlayın.")
                
            tool_name = ctx.message.name
            
            # Get the tool to check its tags/requirements
            try:
                tool = await ctx.fastmcp_context.fastmcp.get_tool(tool_name)
                required_scopes = self._get_tool_required_scopes(
                    tool_name,
                    getattr(tool, 'tags', None)
                )
            except:
                # Fallback to mapping if tool lookup fails
                required_scopes = self._get_tool_required_scopes(tool_name)
            
            # Check permissions
            if required_scopes and not token.has_any_scope(required_scopes):
                missing_scopes = required_scopes - token.scopes
                raise ToolError(
                    f"Bu işlem için gerekli yetkilere ({', '.join(missing_scopes)}) sahip değilsiniz. "
                    f"Mevcut yetkileriniz: {', '.join(token.scopes)}"
                )
            
            logger.debug(f"User {token.username} authorized to use tool '{tool_name}'")
            return await call_next(ctx)
            
        except ToolError:
            # Re-raise ToolError as-is
            raise
        except Exception as e:
            logger.error(f"Error in tool authorization: {e}")
            raise ToolError(f"Yetkilendirme hatası: {str(e)}")


class AuditMiddleware(Middleware):
    """
    Audit middleware for logging tool usage.
    
    This middleware logs all tool calls for auditing and monitoring purposes.
    """
    
    def __init__(self, log_requests: bool = True, log_responses: bool = False):
        """
        Initialize audit middleware.
        
        Args:
            log_requests: Whether to log tool requests
            log_responses: Whether to log tool responses (may contain sensitive data)
        """
        self.log_requests = log_requests
        self.log_responses = log_responses
    
    async def on_call_tool(self, ctx: MiddlewareContext, call_next):
        """
        Log tool calls for audit purposes.
        
        Args:
            ctx: Middleware context
            call_next: Next middleware/handler in chain
            
        Returns:
            Tool execution result
        """
        if not FASTMCP_AVAILABLE:
            return await call_next(ctx)
            
        try:
            token = get_access_token()
            user_info = f"user:{token.username}" if token and hasattr(token, 'username') else "anonymous"
            tool_name = ctx.message.name
            
            if self.log_requests:
                logger.info(f"AUDIT: {user_info} called tool '{tool_name}'")
            
            result = await call_next(ctx)
            
            if self.log_responses:
                logger.info(f"AUDIT: Tool '{tool_name}' completed for {user_info}")
                
            return result
            
        except Exception as e:
            logger.error(f"AUDIT: Tool '{tool_name}' failed for {user_info}: {e}")
            raise
