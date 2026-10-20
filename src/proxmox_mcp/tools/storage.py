"""
Storage-related tools for Proxmox MCP.

This module provides tools for managing and monitoring Proxmox storage:
- Listing all storage pools across the cluster
- Retrieving detailed storage information including:
  * Storage type and content types
  * Usage statistics and capacity
  * Availability status
  * Node assignments

The tools implement fallback mechanisms for scenarios where
detailed storage information might be temporarily unavailable.
"""

from datetime import datetime, timezone
from typing import Any

from mcp.types import TextContent as Content

from ..formatting import ProxmoxFormatters
from ..utils.redaction import redact
from ..validators import validate_node, validate_optional, validate_storage, validate_vmid
from .base import ProxmoxTool

NOTES_MAX = 300


class StorageTools(ProxmoxTool):
    """Tools for managing Proxmox storage.

    Provides functionality for:
    - Retrieving cluster-wide storage information
    - Monitoring storage pool status and health
    - Tracking storage utilization and capacity
    - Managing storage content types

    Implements fallback mechanisms for scenarios where detailed
    storage information might be temporarily unavailable.
    """

    def get_storage(self) -> list[Content]:
        """List storage pools across the cluster with detailed status.

        Retrieves comprehensive information for each storage pool including:
        - Basic identification (name, type)
        - Content types supported (VM disks, backups, ISO images, etc.)
        - Availability status (online/offline)
        - Usage statistics:
          * Used space
          * Total capacity
          * Available space

        Implements a fallback mechanism that returns basic information
        if detailed status retrieval fails for any storage pool.

        Returns:
            List of Content objects containing formatted storage information:
            {
                "storage": "storage-name",
                "type": "storage-type",
                "content": ["content-types"],
                "status": "online/offline",
                "used": bytes,
                "total": bytes,
                "available": bytes
            }

        Raises:
            RuntimeError: If the cluster-wide storage query fails
        """
        try:
            result = self.proxmox.storage.get()
            storage = []

            for store in result:
                # Get detailed storage info including usage
                try:
                    status = (
                        self.proxmox.nodes(store.get("node", "localhost"))
                        .storage(store["storage"])
                        .status.get()
                    )
                    storage.append(
                        {
                            "storage": store["storage"],
                            "type": store["type"],
                            "content": store.get("content", []),
                            "status": "online" if store.get("enabled", True) else "offline",
                            "used": status.get("used", 0),
                            "total": status.get("total", 0),
                            "available": status.get("avail", 0),
                        }
                    )
                except Exception:
                    # If detailed status fails, add basic info
                    storage.append(
                        {
                            "storage": store["storage"],
                            "type": store["type"],
                            "content": store.get("content", []),
                            "status": "online" if store.get("enabled", True) else "offline",
                            "used": 0,
                            "total": 0,
                            "available": 0,
                        }
                    )

            return self._format_response(storage, "storage")
        except Exception as e:
            self._handle_error("get storage", e, privilege_key="get_storage")

    # ---- list_backups -----------------------------------------------------------------

    @staticmethod
    def _has_backup_content(value: Any) -> bool:
        if isinstance(value, str):
            value = [part.strip() for part in value.split(",")]
        return isinstance(value, (list, tuple)) and "backup" in value

    @staticmethod
    def _backup_entry(storage: str, item: dict[str, Any]) -> dict[str, Any]:
        size = item.get("size")
        size = size if isinstance(size, int) and not isinstance(size, bool) else 0
        ctime = item.get("ctime")
        ok = isinstance(ctime, int) and not isinstance(ctime, bool)
        return {
            "volid": redact(str(item.get("volid", ""))),
            "storage": storage,
            "vmid": str(item.get("vmid")) if item.get("vmid") is not None else None,
            "format": item.get("format"),
            "size_bytes": size,
            "size": ProxmoxFormatters.format_bytes(size),
            "ctime": ctime if ok else None,
            "ctime_utc": (
                datetime.fromtimestamp(ctime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                if ok and isinstance(ctime, int)
                else None
            ),
            "notes": redact(str(item.get("notes") or ""))[:NOTES_MAX],
            "protected": bool(item.get("protected")),
        }

    def _storage_backups(self, node: str, storage: str, vmid: str | None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"content": "backup"}
        if vmid is not None:
            params["vmid"] = vmid
        raw = self.proxmox.nodes(node).storage(storage).content.get(**params) or []
        found = []
        for item in raw:
            if not isinstance(item, dict) or item.get("content") != "backup":
                continue
            if vmid is not None and str(item.get("vmid")) != vmid:
                continue
            found.append(self._backup_entry(storage, item))
        return found

    def list_backups(
        self, node: str, storage: str | None = None, vmid: str | None = None
    ) -> list[Content]:
        """List backup volumes (read-only inventory) of one storage or all backup storages."""
        node = validate_node(node)
        storage = validate_optional(validate_storage, storage)
        vmid = validate_optional(validate_vmid, vmid)
        try:
            skipped: list[dict[str, str]] = []
            backups: list[dict[str, Any]] = []
            if storage is not None:
                backups = self._storage_backups(node, storage, vmid)
            else:
                listing = self.proxmox.nodes(node).storage.get(content="backup") or []
                for store in listing:
                    if not isinstance(store, dict):
                        continue
                    if not store.get("enabled", 1) or not store.get("active", 1):
                        continue
                    if not self._has_backup_content(store.get("content")):
                        continue
                    try:
                        name = validate_storage(store.get("storage"))
                        backups.extend(self._storage_backups(node, name, vmid))
                    except Exception as exc:  # reported, never hidden; other storages continue
                        skipped.append(
                            {
                                "storage": redact(str(store.get("storage"))),
                                "reason": redact(str(exc))[:NOTES_MAX],
                            }
                        )
            backups.sort(key=lambda b: (b["ctime"] or 0, b["volid"]), reverse=True)
            payload = {
                "node": node,
                "count": len(backups),
                "backups": backups,
                "skipped": skipped,
            }
            return self._format_response(payload)
        except Exception as e:
            self._handle_error("list backups", e, privilege_key="list_backups", node=node)
