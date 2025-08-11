"""
HTTP-based MCP server implementation for ProxmoxMCP.

This module provides an HTTP transport layer for the MCP server,
supporting both regular HTTP and streamable HTTP transports with
Django authentication integration.
"""

import logging
import json
import os
import sys
import signal
from typing import Optional, Set
from datetime import datetime

try:
    import django
    from django.core.management.base import BaseCommand
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False

try:
    from fastmcp import FastMCP
    FASTMCP_AVAILABLE = True
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
        FASTMCP_AVAILABLE = True
    except ImportError:
        FASTMCP_AVAILABLE = False

from .config.loader import load_config
from .core.logging import setup_logging
from .core.proxmox import ProxmoxManager
from .tools.node import NodeTools
from .tools.vm import VMTools
from .tools.storage import StorageTools
from .tools.cluster import ClusterTools
from .auth import YartuMCPAuthProvider, ScopeRBAC, ProxmoxMCPToken
from .auth.middleware import AuditMiddleware


logger = logging.getLogger("proxmox-mcp.http")


class ProxmoxMCPHTTPServer:
    """
    HTTP-based MCP server with Django authentication.
    
    This server supports:
    - Streamable HTTP transport
    - Django-based authentication
    - RBAC with scopes
    - Audit logging
    """
    
    def __init__(self, 
                 config_path: Optional[str] = None,
                 use_django_auth: bool = True,
                 host: str = "0.0.0.0",
                 port: int = 8812,
                 path: str = "/proxmox-mcp"):
        """
        Initialize the HTTP MCP server.
        
        Args:
            config_path: Path to configuration file
            use_django_auth: Whether to use Django authentication
            host: Server host address
            port: Server port
            path: HTTP path for MCP endpoint
        """
        if not FASTMCP_AVAILABLE:
            raise RuntimeError("FastMCP is not available. Please install fastmcp package.")
            
        self.config = load_config(config_path)
        self.logger = setup_logging(self.config.logging)
        self.use_django_auth = False  # Temporarily disable for testing
        self.host = host
        self.port = port
        self.path = path
        
        # Initialize core components
        self.proxmox_manager = ProxmoxManager(self.config.proxmox, self.config.auth)
        self.proxmox = self.proxmox_manager.get_api()
        
        # Initialize tools
        self.node_tools = NodeTools(self.proxmox)
        self.vm_tools = VMTools(self.proxmox)
        self.storage_tools = StorageTools(self.proxmox)
        self.cluster_tools = ClusterTools(self.proxmox)
        
        # Setup authentication
        self.auth_provider = None
        if self.use_django_auth:
            self.auth_provider = YartuMCPAuthProvider()
            self.logger.info("Django authentication enabled")
        
        # Initialize FastMCP with authentication
        self.mcp = FastMCP("ProxmoxMCP-HTTP")
        
        # Add middleware
        self._setup_middleware()
        
        # Setup tools
        self._setup_tools()

    def _setup_middleware(self) -> None:
        """Setup middleware stack."""
        if self.use_django_auth:
            try:
                # Add RBAC middleware
                rbac_middleware = ScopeRBAC()
                self.mcp.add_middleware(rbac_middleware)
                self.logger.info("RBAC middleware added")
                
                # Add audit middleware
                audit_middleware = AuditMiddleware(log_requests=True, log_responses=False)
                self.mcp.add_middleware(audit_middleware)
                self.logger.info("Audit middleware added")
            except Exception as e:
                self.logger.warning(f"Could not setup middleware: {e}. Running without authentication.")

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
            try:
                result = []
                nodes = self.proxmox.nodes.get()
                for node in nodes:
                    node_name = node.get("node")
                    try:
                        containers = self.proxmox.nodes(node_name).lxc.get()
                        result.extend(containers)
                    except Exception:
                        continue
            except Exception:
                result = []
            return self._format_response(result, "containers")

        # Storage tools
        @self.mcp.tool(description="List storage pools")
        def get_storage():
            return self.storage_tools.get_storage()

        # Cluster tools
        @self.mcp.tool(description="Get cluster status")
        def get_cluster_status():
            return self.cluster_tools.get_cluster_status()

        # Health check
        @self.mcp.tool(description="Health check")
        def health():
            return [{"type": "text", "text": json.dumps({
                "status": "ok",
                "server": "ProxmoxMCP-HTTP",
                "timestamp": datetime.now().isoformat(),
                "auth": "enabled" if self.use_django_auth else "disabled"
            })}]

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
        def signal_handler(signum, frame):
            self.logger.info("Received signal to shutdown HTTP server...")
            sys.exit(0)

        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            self.logger.info(f"Starting ProxmoxMCP HTTP server on {self.host}:{self.port}{self.path}")
            self.logger.info(f"Authentication: {'Django' if self.use_django_auth else 'Disabled'}")
            
            # Run with HTTP transport (FastMCP 2.11.2 style)
            import uvicorn
            
            # Get the HTTP app from FastMCP (using new API)
            try:
                app = self.mcp.http_app
            except AttributeError:
                # Fallback to deprecated method if needed
                app = self.mcp.streamable_http_app
            
            # Mount the app on the specified path
            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware
            
            root_app = FastAPI()
            root_app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            
            # Mount the MCP app on the specified path
            root_app.mount(self.path, app)
            
            # Run with uvicorn
            uvicorn.run(
                root_app,
                host=self.host,
                port=self.port,
                log_level="info"
            )
        except Exception as e:
            self.logger.error(f"HTTP server error: {e}")
            sys.exit(1)


class ProxmoxMCPCommand:
    """
    Django management command for ProxmoxMCP HTTP server.
    
    This class can be used as a Django management command when Django is available,
    or as a standalone command runner.
    """
    
    help = "ProxmoxMCP HTTP Server with Django Authentication"
    
    def __init__(self):
        self.server = None
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--host',
            type=str,
            default='0.0.0.0',
            help='Server host (default: 0.0.0.0)'
        )
        parser.add_argument(
            '--port',
            type=int,
            default=8812,
            help='Server port (default: 8812)'
        )
        parser.add_argument(
            '--path',
            type=str,
            default='/proxmox-mcp',
            help='HTTP path (default: /proxmox-mcp)'
        )
        parser.add_argument(
            '--config',
            type=str,
            help='Configuration file path'
        )
        parser.add_argument(
            '--no-auth',
            action='store_true',
            help='Disable Django authentication'
        )
    
    def handle(self, *args, **options):
        """Handle the command execution."""
        if DJANGO_AVAILABLE:
            django.setup()
            
        config_path = options.get('config') or os.getenv('PROXMOX_MCP_CONFIG')
        
        self.server = ProxmoxMCPHTTPServer(
            config_path=config_path,
            use_django_auth=not options.get('no_auth', False),
            host=options.get('host', '0.0.0.0'),
            port=options.get('port', 8812),
            path=options.get('path', '/proxmox-mcp')
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
