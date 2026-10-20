"""
HTTP-based MCP server implementation for ProxmoxMCP.

Thin wrapper around :func:`proxmox_mcp.app.create_app`.  Serves the MCP tools over
streamable HTTP, protected by API-key authentication (see ``proxmox_mcp.auth.apikey``).
The server fails closed: it refuses to start without configured key digests unless
explicitly run with ``--no-auth`` on a loopback address.
"""

import logging
import os
import sys
from typing import List, Optional

from .app import create_app
from .auth.apikey import ENV_HASHES
from .auth.policy import LOOPBACK_HOSTS, AuthConfigError
from .config.loader import load_config
from .core.logging import setup_logging
from .utils.redaction import safe_error_message

__all__ = ["AuthConfigError", "LOOPBACK_HOSTS", "ProxmoxMCPHTTPServer", "build_parser", "main"]

logger = logging.getLogger("proxmox-mcp.http")


class ProxmoxMCPHTTPServer:
    """
    HTTP-based MCP server with API-key authentication.

    Fails closed: without key digests (``api_key_digests`` or the
    ``PROXMOX_MCP_API_KEY_HASHES`` env var) construction raises
    ``AuthConfigError``, unless ``insecure_no_auth=True`` on a loopback host.
    """

    def __init__(self,
                 config_path: Optional[str] = None,
                 host: str = "127.0.0.1",
                 port: int = 8812,
                 path: str = "/proxmox-mcp",
                 api_key_digests: Optional[List[str]] = None,
                 insecure_no_auth: bool = False):
        """
        Initialize the HTTP MCP server.

        Args:
            config_path: Path to configuration file
            host: Server host address (default loopback)
            port: Server port
            path: HTTP path for MCP endpoint
            api_key_digests: sha256 hex digests of accepted API keys; defaults
                to the PROXMOX_MCP_API_KEY_HASHES environment variable, then
                the config file (http.api_key_digests)
            insecure_no_auth: Disable authentication (loopback hosts only)
        """
        self.host = host
        self.port = port
        self.path = path
        self.insecure_no_auth = insecure_no_auth
        self.config = load_config(config_path)
        self.logger = setup_logging(self.config.logging)

        self.app = create_app(
            self.config,
            "http",
            host=host,
            port=port,
            path=path,
            api_key_digests=api_key_digests,
            insecure_no_auth=insecure_no_auth,
        )
        self.mcp = self.app.mcp
        self.proxmox_manager = self.app.manager
        self.proxmox = self.proxmox_manager.get_api()
        self.node_tools = self.app.node_tools
        self.vm_tools = self.app.vm_tools
        self.storage_tools = self.app.storage_tools
        self.cluster_tools = self.app.cluster_tools
        self.auth_enabled = self.app.auth_state == "api-key"

    def auth_state(self) -> str:
        """Truthful auth state: 'api-key' or 'disabled'."""
        return self.app.auth_state

    def build_app(self):
        """The ASGI app that is actually served (auth middleware included)."""
        return self.app.asgi

    def run(self) -> None:
        """Start the HTTP MCP server (uvicorn serving ``build_app()``)."""
        try:
            self.logger.info(
                f"Starting ProxmoxMCP HTTP server on {self.host}:{self.port}{self.path}"
            )
            self.logger.info(f"Authentication: {self.auth_state()}")
            self.app.run()
        except Exception as e:
            self.logger.error(f"HTTP server error: {e}")
            sys.exit(1)


def build_parser():
    """Command line parser for the standalone HTTP server."""
    import argparse

    parser = argparse.ArgumentParser(description='ProxmoxMCP HTTP Server')
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
    return parser


def main():
    """Main entry point for standalone execution."""
    args = build_parser().parse_args()

    try:
        server = ProxmoxMCPHTTPServer(
            config_path=args.config or os.getenv('PROXMOX_MCP_CONFIG'),
            host=args.host,
            port=args.port,
            path=args.path,
            insecure_no_auth=args.no_auth,
        )
        server.run()
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {safe_error_message(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
