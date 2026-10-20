"""
HTTP-based MCP server implementation for ProxmoxMCP.

Serves the MCP tools over streamable HTTP, protected by API-key
authentication (see ``proxmox_mcp.auth.apikey``).  The server fails closed:
it refuses to start without configured key digests unless explicitly run
with ``--no-auth`` on a loopback address.
"""

import json
import logging
import os
import sys
import warnings
from datetime import datetime
from typing import List, Optional

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth.apikey import APIKeyAuthMiddleware, ENV_HASHES, digests_from_env, normalize_digests
from .auth.hostguard import LoopbackHostGuardMiddleware
from .config.loader import load_config
from .core.logging import setup_logging
from .core.proxmox import ProxmoxManager
from .tools.node import NodeTools
from .tools.vm import VMTools
from .tools.storage import StorageTools
from .tools.cluster import ClusterTools

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

logger = logging.getLogger("proxmox-mcp.http")


class AuthConfigError(ValueError):
    """Raised when the HTTP server's authentication setup is unsafe or missing."""


class ProxmoxMCPHTTPServer:
    """
    HTTP-based MCP server with API-key authentication.

    Fails closed: without key digests (``api_key_digests`` or the
    ``PROXMOX_MCP_API_KEY_HASHES`` env var) construction raises
    ``AuthConfigError``, unless ``insecure_no_auth=True`` on a loopback host.
    """

    def __init__(self,
                 config_path: Optional[str] = None,
                 use_django_auth: Optional[bool] = None,
                 host: str = "127.0.0.1",
                 port: int = 8812,
                 path: str = "/proxmox-mcp",
                 api_key_digests: Optional[List[str]] = None,
                 insecure_no_auth: bool = False):
        """
        Initialize the HTTP MCP server.

        Args:
            config_path: Path to configuration file
            use_django_auth: Deprecated no-op alias, ignored
            host: Server host address (default loopback)
            port: Server port
            path: HTTP path for MCP endpoint
            api_key_digests: sha256 hex digests of accepted API keys; defaults
                to the PROXMOX_MCP_API_KEY_HASHES environment variable
            insecure_no_auth: Disable authentication (loopback hosts only)
        """
        if use_django_auth is not None:
            warnings.warn(
                "use_django_auth is deprecated and ignored; API-key auth is used",
                DeprecationWarning,
                stacklevel=2,
            )
        self.host = host
        self.port = port
        self.path = path
        self.insecure_no_auth = insecure_no_auth
        self.api_key_digests = self._resolve_digests(api_key_digests)
        self.auth_enabled = bool(self.api_key_digests)
        self._check_auth_policy()

        self.config = load_config(config_path)
        self.logger = setup_logging(self.config.logging)
        if not self.auth_enabled:
            self.logger.warning(
                "AUTHENTICATION DISABLED (--no-auth): all MCP tools, including VM "
                "create/delete/exec, are open to anyone who can reach %s:%s",
                self.host, self.port,
            )

        # Initialize core components
        self.proxmox_manager = ProxmoxManager(self.config.proxmox, self.config.auth)
        self.proxmox = self.proxmox_manager.get_api()

        # Initialize tools
        self.node_tools = NodeTools(self.proxmox)
        self.vm_tools = VMTools(self.proxmox)
        self.storage_tools = StorageTools(self.proxmox)
        self.cluster_tools = ClusterTools(self.proxmox)

        self.mcp = FastMCP("ProxmoxMCP-HTTP")
        self._setup_tools()
        self._setup_health_route()

    @staticmethod
    def _resolve_digests(explicit: Optional[List[str]]) -> List[str]:
        try:
            if explicit is not None:
                return normalize_digests(explicit)
            return digests_from_env()
        except ValueError as e:
            raise AuthConfigError(str(e)) from e

    def _check_auth_policy(self) -> None:
        """Fail closed on missing keys / unsafe --no-auth."""
        if self.auth_enabled:
            return
        if not self.insecure_no_auth:
            raise AuthConfigError(
                f"No API key digests configured. Set {ENV_HASHES} (comma-separated "
                "sha256 hex digests; generate with `python -m proxmox_mcp.auth.apikey`) "
                "or, for local development only, pass --no-auth on a loopback host."
            )
        if self.host not in LOOPBACK_HOSTS:
            raise AuthConfigError(
                f"--no-auth is only allowed on loopback (127.0.0.1, ::1, localhost), "
                f"not on {self.host!r}. Configure {ENV_HASHES} instead."
            )

    def auth_state(self) -> str:
        """Truthful auth state: 'api-key' or 'disabled'."""
        return "api-key" if self.auth_enabled else "disabled"

    def _setup_health_route(self) -> None:
        @self.mcp.custom_route("/health", methods=["GET"])
        async def health_route(request: Request) -> JSONResponse:
            return JSONResponse(self._health_payload())

    def _health_payload(self) -> dict:
        return {
            "status": "ok",
            "server": "ProxmoxMCP-HTTP",
            "timestamp": datetime.now().isoformat(),
            "auth": self.auth_state(),
        }

    def _http_middleware(self) -> List[Middleware]:
        if not self.auth_enabled:
            # No-auth dev mode: still refuse DNS-rebinding / cross-site browser requests.
            return [Middleware(LoopbackHostGuardMiddleware)]
        return [Middleware(APIKeyAuthMiddleware, digests=self.api_key_digests)]

    def build_app(self):
        """Build the ASGI app that is actually served (auth middleware included)."""
        return self.mcp.http_app(path=self.path, middleware=self._http_middleware())

    def _setup_tools(self) -> None:
        """Register MCP tools with appropriate scope tags."""
        
        # Node tools (read-only)
        @self.mcp.tool(description="List all Proxmox nodes")
        def get_nodes():
            return self.node_tools.get_nodes()

        @self.mcp.tool(description="Get detailed node status")
        def get_node_status(node: str):
            return self.node_tools.get_node_status(node)

        # VM tools with different permission levels
        @self.mcp.tool(description="List all VMs")
        def get_vms():
            return self.vm_tools.get_vms()

        @self.mcp.tool(description="Get VM resource usage")
        def get_vm_usage(node: str, vmid: str):
            return self.vm_tools.get_vm_usage(node, vmid)

        @self.mcp.tool(description="Create a new VM")
        def create_vm(node: str, vmid: str, name: str, cpus: int, memory: int, disk_size: int,
                     storage: Optional[str] = None, ostype: Optional[str] = None,
                     iso_name: Optional[str] = None, iso_storage: Optional[str] = None):
            return self.vm_tools.create_vm(node, vmid, name, cpus, memory, disk_size,
                                         storage, ostype, iso_name, iso_storage)

        @self.mcp.tool(description="Start a VM")
        def start_vm(node: str, vmid: str):
            return self.vm_tools.start_vm(node, vmid)

        @self.mcp.tool(description="Stop a VM")
        def stop_vm(node: str, vmid: str):
            return self.vm_tools.stop_vm(node, vmid)

        @self.mcp.tool(description="Shutdown a VM gracefully")
        def shutdown_vm(node: str, vmid: str):
            return self.vm_tools.shutdown_vm(node, vmid)

        @self.mcp.tool(description="Reset a VM")
        def reset_vm(node: str, vmid: str):
            return self.vm_tools.reset_vm(node, vmid)

        @self.mcp.tool(description="Delete a VM")
        def delete_vm(node: str, vmid: str, force: bool = False):
            return self.vm_tools.delete_vm(node, vmid, force)

        @self.mcp.tool(description="Execute command in VM")
        async def execute_vm_command(node: str, vmid: str, command: str):
            return await self.vm_tools.execute_command(node, vmid, command)

        @self.mcp.tool(description="Create VM snapshot")
        def create_snapshot(node: str, vmid: str, name: str, 
                          description: Optional[str] = None, vmstate: bool = False):
            return self.vm_tools.create_snapshot(node, vmid, name, description, vmstate)

        @self.mcp.tool(description="Rollback VM snapshot")
        def rollback_snapshot(node: str, vmid: str, name: str):
            return self.vm_tools.rollback_snapshot(node, vmid, name)

        # Container tools
        @self.mcp.tool(description="List all containers")
        def get_containers():
            result = self.cluster_tools.list_containers()
            return self._format_response(result, "containers")

        # Storage tools
        @self.mcp.tool(description="List storage pools")
        def get_storage():
            return self.storage_tools.get_storage()

        # Cluster tools
        @self.mcp.tool(description="Get cluster status")
        def get_cluster_status():
            return self.cluster_tools.get_cluster_status()

        # Health check (tool form; the unauthenticated HTTP route is /health)
        @self.mcp.tool(description="Health check")
        def health():
            return [{"type": "text", "text": json.dumps(self._health_payload())}]

    def _format_response(self, data, data_type):
        """Format response data for MCP."""
        from mcp.types import TextContent as Content
        from .formatting import ProxmoxFormatters
        
        if data_type == "containers":
            formatted = ProxmoxFormatters.format_containers(data)
        else:
            formatted = json.dumps(data, indent=2)
            
        return [Content(type="text", text=formatted)]

    def run(self) -> None:
        """
        Start the HTTP MCP server.
        
        Runs the server with streamable HTTP transport on the configured
        host and port.
        """
        # Signals are left to uvicorn/FastMCP so shutdown stays graceful.
        try:
            self.logger.info(f"Starting ProxmoxMCP HTTP server on {self.host}:{self.port}{self.path}")
            self.logger.info(f"Authentication: {self.auth_state()}")
            
            # Run with FastMCP's built-in HTTP transport
            self.mcp.run(
                transport="http",
                host=self.host,
                port=self.port,
                path=self.path,
                middleware=self._http_middleware(),
            )
        except Exception as e:
            self.logger.error(f"HTTP server error: {e}")
            sys.exit(1)


class ProxmoxMCPCommand:
    """Standalone command runner for the ProxmoxMCP HTTP server."""

    help = "ProxmoxMCP HTTP Server with API-key authentication"

    def __init__(self):
        self.server = None

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument('--host', type=str, default='127.0.0.1',
                            help='Server host (default: 127.0.0.1)')
        parser.add_argument('--port', type=int, default=8812,
                            help='Server port (default: 8812)')
        parser.add_argument('--path', type=str, default='/proxmox-mcp',
                            help='HTTP path (default: /proxmox-mcp)')
        parser.add_argument('--config', type=str, help='Configuration file path')
        parser.add_argument(
            '--no-auth', action='store_true',
            help=f'Disable authentication (loopback only; otherwise set {ENV_HASHES})')

    def handle(self, *args, **options):
        """Handle the command execution."""
        config_path = options.get('config') or os.getenv('PROXMOX_MCP_CONFIG')

        self.server = ProxmoxMCPHTTPServer(
            config_path=config_path,
            host=options.get('host', '127.0.0.1'),
            port=options.get('port', 8812),
            path=options.get('path', '/proxmox-mcp'),
            insecure_no_auth=bool(options.get('no_auth', False)),
        )

        self.server.run()


def main():
    """Main entry point for standalone execution."""
    import argparse

    parser = argparse.ArgumentParser(description='ProxmoxMCP HTTP Server')
    command = ProxmoxMCPCommand()
    command.add_arguments(parser)

    args = parser.parse_args()
    options = vars(args)

    try:
        command.handle(**options)
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
