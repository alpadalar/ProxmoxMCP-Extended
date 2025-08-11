"""
Django management command to run ProxmoxMCP HTTP server.

Usage:
    python manage.py run_mcp_server --host 0.0.0.0 --port 8812 --path /proxmox-mcp
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from django.core.management.base import BaseCommand
from django.conf import settings

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

from ...server_http import ProxmoxMCPHTTPServer
from ...auth import YartuMCPAuthProvider, ScopeRBAC


class Command(BaseCommand):
    """
    Django management command for ProxmoxMCP HTTP server.
    
    This command integrates with Django's authentication system and
    provides a streamable HTTP transport for MCP tools.
    """
    
    help = "Run ProxmoxMCP HTTP Server with Django Authentication"
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--host',
            type=str,
            default='0.0.0.0',
            help='Server host address (default: 0.0.0.0)'
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
            help='HTTP endpoint path (default: /proxmox-mcp)'
        )
        parser.add_argument(
            '--config',
            type=str,
            help='ProxmoxMCP configuration file path'
        )
        parser.add_argument(
            '--no-auth',
            action='store_true',
            help='Disable Django authentication (for testing)'
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable debug logging'
        )
        parser.add_argument(
            '--log-file',
            type=str,
            help='Log file path (overrides config)'
        )
    
    def handle(self, *args, **options):
        """Handle the command execution."""
        # Set up logging level
        if options['debug']:
            import logging
            logging.getLogger('proxmox-mcp').setLevel(logging.DEBUG)
            
        # Get configuration path
        config_path = options.get('config') or os.getenv('PROXMOX_MCP_CONFIG')
        if not config_path:
            self.stdout.write(
                self.style.WARNING(
                    'No configuration file specified. Set PROXMOX_MCP_CONFIG environment variable '
                    'or use --config option.'
                )
            )
        
        # Display startup information
        self.stdout.write(self.style.SUCCESS("🚀 Starting ProxmoxMCP HTTP Server"))
        self.stdout.write(f"   Host: {options['host']}")
        self.stdout.write(f"   Port: {options['port']}")
        self.stdout.write(f"   Path: {options['path']}")
        self.stdout.write(f"   Auth: {'Disabled' if options['no_auth'] else 'Django Integration'}")
        
        if config_path:
            self.stdout.write(f"   Config: {config_path}")
        
        # Create and start server
        try:
            server = ProxmoxMCPHTTPServer(
                config_path=config_path,
                use_django_auth=not options['no_auth'],
                host=options['host'],
                port=options['port'],
                path=options['path']
            )
            
            # Override log file if specified
            if options.get('log_file'):
                server.logger.handlers[0].baseFilename = options['log_file']
            
            self.stdout.write(self.style.SUCCESS("✅ Server initialized successfully"))
            self.stdout.write("")
            self.stdout.write("🔗 Access Information:")
            self.stdout.write(f"   Endpoint: http://{options['host']}:{options['port']}{options['path']}")
            self.stdout.write("   Protocol: MCP over HTTP (streamable)")
            
            if not options['no_auth']:
                self.stdout.write("")
                self.stdout.write("🔒 Authentication:")
                self.stdout.write("   Use Authorization: Bearer <your-token> header")
                self.stdout.write("   Scopes: user, write, admin")
            
            self.stdout.write("")
            self.stdout.write("📋 Available Tools:")
            
            # List available tools with their required scopes
            tool_info = {
                "get_nodes": "user",
                "get_node_status": "user", 
                "get_vms": "user",
                "get_containers": "user",
                "get_storage": "user",
                "get_cluster_status": "user",
                "get_vm_usage": "user",
                "health": "user",
                "start_vm": "write",
                "shutdown_vm": "write",
                "execute_vm_command": "write",
                "create_snapshot": "write",
                "rollback_snapshot": "write",
                "create_vm": "admin",
                "stop_vm": "admin",
                "reset_vm": "admin", 
                "delete_vm": "admin"
            }
            
            for tool, scope in tool_info.items():
                scope_color = {
                    "user": self.style.SUCCESS,
                    "write": self.style.WARNING,
                    "admin": self.style.ERROR
                }.get(scope, self.style.SUCCESS)
                
                self.stdout.write(f"   • {tool:<20} [{scope_color(scope)}]")
            
            self.stdout.write("")
            self.stdout.write("Press Ctrl+C to stop the server")
            self.stdout.write("=" * 60)
            
            # Start server
            server.run()
            
        except KeyboardInterrupt:
            self.stdout.write("\n")
            self.stdout.write(self.style.SUCCESS("🛑 Server stopped gracefully"))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Server error: {e}")
            )
            if options['debug']:
                import traceback
                traceback.print_exc()
            sys.exit(1)
