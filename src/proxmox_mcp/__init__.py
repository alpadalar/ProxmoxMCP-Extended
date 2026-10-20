"""
Proxmox MCP Server - A Model Context Protocol server for interacting with Proxmox hypervisors.

This package exposes symbols lazily to avoid import side-effects when
running `python -m proxmox_mcp.server`.
"""

from typing import TYPE_CHECKING, Any

__version__ = "1.0.0"
__all__ = ["ProxmoxMCPServer", "__version__"]

if TYPE_CHECKING:
    # For type checkers only; avoids runtime import
    from .server import ProxmoxMCPServer as ProxmoxMCPServer


def __getattr__(name: str) -> Any:  # pragma: no cover - trivial lazy import
    if name == "ProxmoxMCPServer":
        from .server import ProxmoxMCPServer as _ProxmoxMCPServer

        return _ProxmoxMCPServer
    raise AttributeError(f"module 'proxmox_mcp' has no attribute {name!r}")
