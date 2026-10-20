"""
Stdio MCP server for Proxmox.

Thin wrapper around :func:`proxmox_mcp.app.create_app`: loads configuration, sets up
logging and runs the stdio transport.  All tools come from the shared registry
(``proxmox_mcp.tools.registry``).
"""

import argparse
import os
import sys
from collections.abc import Mapping
from typing import Any

from .app import create_app
from .config.loader import add_policy_flags, load_config, policy_cli_overrides
from .core.logging import setup_logging
from .utils.redaction import safe_error_message


class ProxmoxMCPServer:
    """Main server class for Proxmox MCP (stdio)."""

    def __init__(
        self,
        config_path: str | None = None,
        cli_overrides: Mapping[str, Any] | None = None,
    ):
        """Initialize the server.

        Args:
            config_path: Path to configuration file
            cli_overrides: Optional nested overrides (highest precedence)
        """
        self.config = load_config(config_path, cli_overrides=cli_overrides)
        self.logger = setup_logging(self.config.logging)

        self.app = create_app(self.config, "stdio")
        self.mcp = self.app.mcp
        self.proxmox_manager = self.app.manager
        self.proxmox = self.proxmox_manager.get_api()
        self.node_tools = self.app.node_tools
        self.vm_tools = self.app.vm_tools
        self.storage_tools = self.app.storage_tools
        self.cluster_tools = self.app.cluster_tools

    @property
    def _tests_passed(self) -> bool | None:
        return self.app.tests_passed

    @_tests_passed.setter
    def _tests_passed(self, value: bool | None) -> None:
        self.app.tests_passed = value

    def start(self) -> None:
        """Start the MCP server.

        Initializes the server with:
        - Shutdown handled by fastmcp (KeyboardInterrupt / SIGTERM)
        - Async runtime for handling concurrent requests
        - Error handling and logging

        The server runs until terminated by a signal or fatal error.
        """
        try:
            # Optionally run tests before serving
            run_tests = os.getenv("RUN_TESTS_ON_START", "0").lower() in ("1", "true", "yes", "on")
            if run_tests:
                import subprocess

                self.logger.info("Running startup tests (pytest)...")
                env = os.environ.copy()
                # Ensure src on PYTHONPATH for tests
                extra = ":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
                env["PYTHONPATH"] = f"{os.getcwd()}/src" + extra
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
                self._tests_passed = result.returncode == 0
                if not self._tests_passed:
                    self.logger.error(
                        "Startup tests failed. Health will be 'degraded'. Output:\n"
                        + result.stdout.decode()
                    )
                else:
                    self.logger.info("Startup tests passed.")

            self.logger.info("Starting MCP server...")
            self.mcp.run(transport="stdio")
        except Exception as e:
            self.logger.error(f"Server error: {e}")
            sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    """Console script entry point for ``proxmox-mcp``."""
    parser = argparse.ArgumentParser(
        prog="proxmox-mcp",
        description="Proxmox MCP server (stdio transport).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the config JSON file (default: $PROXMOX_MCP_CONFIG)",
    )
    parser.add_argument("--log-level", default=None, help="Override logging level")
    parser.add_argument("--log-file", default=None, help="Override log file path")
    parser.add_argument(
        "--verify-ssl",
        default=None,
        help="Override TLS verification (true/false, 1/0, yes/no, on/off)",
    )
    parser.add_argument("--ca-bundle", default=None, help="CA bundle file for TLS verification")
    add_policy_flags(parser)
    args = parser.parse_args(argv)

    cli_overrides: dict[str, Any] = {}
    for section, key, value in (
        ("logging", "level", args.log_level),
        ("logging", "file", args.log_file),
        ("proxmox", "verify_ssl", args.verify_ssl),
        ("proxmox", "ca_bundle", args.ca_bundle),
    ):
        if value is not None:
            cli_overrides.setdefault(section, {})[key] = value
    cli_overrides.update(policy_cli_overrides(args))

    config_path = args.config or os.getenv("PROXMOX_MCP_CONFIG")
    if not config_path:
        print(
            "Error: config path required (use --config or set PROXMOX_MCP_CONFIG)",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        server = ProxmoxMCPServer(config_path, cli_overrides=cli_overrides)
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {safe_error_message(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
