"""
Django-based authentication system for ProxmoxMCP.

This module provides integration with Django authentication system,
including custom auth providers and RBAC middleware.
"""

from .providers import YartuMCPAuthProvider
from .middleware import ScopeRBAC
from .models import ProxmoxMCPToken

__all__ = ["YartuMCPAuthProvider", "ScopeRBAC", "ProxmoxMCPToken"]
