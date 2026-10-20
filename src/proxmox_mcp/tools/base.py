"""
Base classes and utilities for Proxmox MCP tools.

This module provides the foundation for all Proxmox MCP tools, including:
- Base tool class with common functionality
- Response formatting utilities
- Error handling mechanisms
- Logging setup

All tool implementations inherit from the ProxmoxTool base class to ensure
consistent behavior and error handling across the MCP server.
"""

import logging
from collections.abc import Callable
from typing import Any

import requests
from mcp.types import TextContent as Content
from proxmoxer import ProxmoxAPI
from proxmoxer.core import ResourceException

from ..formatting import ProxmoxTemplates
from ..utils.redaction import redact
from .pve_compat import TaskFailedError, translate_pve_error


class ProxmoxTool:
    """Base class for Proxmox MCP tools.

    This class provides common functionality used by all Proxmox tool implementations:
    - Proxmox API access
    - Standardized logging
    - Response formatting
    - Error handling

    All tool classes should inherit from this base class to ensure consistent
    behavior and error handling across the MCP server.
    """

    def __init__(self, proxmox_api: ProxmoxAPI):
        """Initialize the tool.

        Args:
            proxmox_api: Initialized ProxmoxAPI instance
        """
        self.proxmox = proxmox_api
        self._pve_major: Callable[[], int | None] = lambda: None
        self.logger = logging.getLogger(f"proxmox-mcp.{self.__class__.__name__.lower()}")

    def _format_response(self, data: Any, resource_type: str | None = None) -> list[Content]:
        """Format response data into MCP content using templates.

        This method handles formatting of various Proxmox resource types into
        consistent MCP content responses. It uses specialized templates for
        different resource types (nodes, VMs, storage, etc.) and falls back
        to JSON formatting for unknown types.

        Args:
            data: Raw data from Proxmox API to format
            resource_type: Type of resource for template selection. Valid types:
                         'nodes', 'node_status', 'vms', 'storage', 'containers', 'cluster'

        Returns:
            List of Content objects formatted according to resource type
        """
        if resource_type == "nodes":
            formatted = ProxmoxTemplates.node_list(data)
        elif resource_type == "node_status":
            # For node_status, data should be a tuple of (node_name, status_dict)
            if isinstance(data, tuple) and len(data) == 2:
                formatted = ProxmoxTemplates.node_status(data[0], data[1])
            else:
                formatted = ProxmoxTemplates.node_status("unknown", data)
        elif resource_type == "vms":
            formatted = ProxmoxTemplates.vm_list(data)
        elif resource_type == "storage":
            formatted = ProxmoxTemplates.storage_list(data)
        elif resource_type == "containers":
            formatted = ProxmoxTemplates.container_list(data)
        elif resource_type == "cluster":
            formatted = ProxmoxTemplates.cluster_status(data)
        else:
            # Fallback to JSON formatting for unknown types
            import json

            formatted = json.dumps(data, indent=2)

        return [Content(type="text", text=formatted)]

    def _handle_error(
        self,
        operation: str,
        error: Exception,
        privilege_key: str | None = None,
        node: str | None = None,
        vmid: str | None = None,
    ) -> None:
        """Handle and log errors from Proxmox operations.

        ValueError (including validator errors) and TaskFailedError are re-raised unchanged. Proxmox API
        errors and connection failures are translated by ``translate_pve_error`` from the
        HTTP status code (403 names the missing privilege and ACL path). The legacy text
        based fallback below applies ONLY to other exception types.

        Args:
            operation: Description of the operation that failed (e.g., "get node status")
            error: The exception that occurred during the operation
            privilege_key: Key into ``OPERATION_PRIVILEGES`` for permission hints
            node: Node name, used in privilege hints
            vmid: VM id, used in privilege hints

        Raises:
            ValueError: For invalid input, missing resources, or permission issues
            RuntimeError: For unexpected errors or API failures
        """
        error_msg = redact(str(error))
        self.logger.error(f"Failed to {redact(operation)}: {error_msg}")

        if isinstance(error, (ValueError, TaskFailedError)):
            raise error
        if isinstance(error, ResourceException) or isinstance(
            error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
        ):
            raise translate_pve_error(
                error,
                operation,
                node=node,
                vmid=vmid,
                privilege_key=privilege_key,
                major=self._pve_major(),
            ) from None

        if "not found" in error_msg.lower():
            raise ValueError(f"Resource not found: {error_msg}")
        if "permission denied" in error_msg.lower():
            raise ValueError(f"Permission denied: {error_msg}")
        if "invalid" in error_msg.lower():
            raise ValueError(f"Invalid input: {error_msg}")

        raise RuntimeError(f"Failed to {redact(operation)}: {error_msg}")
