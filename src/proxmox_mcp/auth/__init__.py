"""API-key authentication and loopback host guard for the HTTP transport.

Names are resolved lazily so ``python -m proxmox_mcp.auth.apikey`` does not trigger the runpy
"found in sys.modules" warning (the package must not import ``apikey`` eagerly).
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .apikey import APIKeyAuthMiddleware, hash_api_key, resolve_digests
    from .policy import AuthConfigError, AuthPolicy, resolve_auth_policy

_EXPORTS = {
    "APIKeyAuthMiddleware": ".apikey",
    "hash_api_key": ".apikey",
    "resolve_digests": ".apikey",
    "AuthConfigError": ".policy",
    "AuthPolicy": ".policy",
    "resolve_auth_policy": ".policy",
}

__all__ = [
    "APIKeyAuthMiddleware",
    "AuthConfigError",
    "AuthPolicy",
    "hash_api_key",
    "resolve_auth_policy",
    "resolve_digests",
]


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module, __name__), name)
