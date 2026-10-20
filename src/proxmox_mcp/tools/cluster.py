"""
Cluster-related tools for Proxmox MCP.

This module provides tools for monitoring and managing Proxmox clusters:
- Retrieving overall cluster health status
- Monitoring quorum status and node count
- Tracking cluster resources and configuration
- Checking cluster-wide service availability

The tools provide essential information for maintaining
cluster health and ensuring proper operation.
"""
from typing import Any, Dict, List
from mcp.types import TextContent as Content
from ..utils.redaction import redact
from .base import ProxmoxTool
from .definitions import GET_CLUSTER_STATUS_DESC

TEXT_MAX = 300
_SERVICE_KEYS = ('sid', 'node', 'state', 'request_state', 'crm_state')
_RESOURCE_KEYS = (
    'sid', 'type', 'state', 'group', 'max_relocate', 'max_restart', 'failback', 'comment',
)
_TEXT_KEYS = ('status', 'comment', 'group')


def _clean(item: Dict[str, Any], keys: Any) -> Dict[str, Any]:
    """Whitelist ``keys`` that are present; free text is redacted and capped."""
    out: Dict[str, Any] = {}
    for key in keys:
        if key not in item:
            continue
        value = item[key]
        if key in _TEXT_KEYS and value is not None:
            value = redact(str(value))[:TEXT_MAX]
        elif isinstance(value, str):
            value = value[:TEXT_MAX]
        out[key] = value
    return out


class ClusterTools(ProxmoxTool):
    """Tools for managing Proxmox cluster.
    
    Provides functionality for:
    - Monitoring cluster health and status
    - Tracking quorum and node membership
    - Managing cluster-wide resources
    - Verifying cluster configuration
    
    Essential for maintaining cluster health and ensuring
    proper operation of the Proxmox environment.
    """

    def list_containers(self) -> List[Dict[str, Any]]:
        """Aggregate LXC containers across nodes.

        A node whose listing fails is skipped with a redacted warning; failure to list
        the nodes themselves is raised (never reported as "no containers").
        """
        try:
            nodes = self.proxmox.nodes.get()
        except Exception as e:
            self._handle_error("list nodes for containers", e, privilege_key="get_containers")
        result: List[Dict[str, Any]] = []
        for node in nodes:
            node_name = node.get("node")
            try:
                result.extend(self.proxmox.nodes(node_name).lxc.get())
            except Exception as e:
                self.logger.warning(
                    f"Skipping containers of node {redact(str(node_name))}: {redact(str(e))}"
                )
        return result

    def get_cluster_status(self) -> List[Content]:
        """Get overall Proxmox cluster health and configuration status.

        Retrieves comprehensive cluster information including:
        - Cluster name and identity
        - Quorum status (essential for cluster operations)
        - Active node count and health
        - Resource distribution and status
        
        This information is critical for:
        - Ensuring cluster stability
        - Monitoring node membership
        - Verifying resource availability
        - Detecting potential issues

        Returns:
            List of Content objects containing formatted cluster status:
            {
                "name": "cluster-name",
                "quorum": true/false,
                "nodes": count,
                "resources": [
                    {
                        "type": "resource-type",
                        "status": "status"
                    }
                ]
            }

        Raises:
            RuntimeError: If cluster status query fails due to:
                        - Network connectivity issues
                        - Authentication problems
                        - API endpoint failures
        """
        try:
            result = self.proxmox.cluster.status.get()
        
            first_item = result[0] if result and len(result) > 0 else {}
            status = {
                "name": first_item.get("name") if first_item else None,
                "quorum": first_item.get("quorate") if first_item else None,
                "nodes": len([node for node in result if node.get("type") == "node"]) if result else 0,
                "resources": [res for res in result if res.get("type") == "resource"] if result else []
            }
            return self._format_response(status, "cluster")
        except Exception as e:
            self._handle_error("get cluster status", e, privilege_key="get_cluster_status")

    def get_ha_status(self) -> List[Content]:
        """Read-only HA overview: quorum, master, LRMs, services and configured resources.

        Issues exactly two GET calls (cluster/ha/status/current and cluster/ha/resources);
        no HA write endpoint is touched. Output keys are whitelisted.
        """
        try:
            status_items = self.proxmox.cluster.ha.status.current.get() or []
            resource_items = self.proxmox.cluster.ha.resources.get() or []
            quorate = None
            master = None
            lrm: List[Dict[str, Any]] = []
            services: List[Dict[str, Any]] = []
            for item in status_items:
                if not isinstance(item, dict):
                    continue
                kind = item.get("type")
                if kind == "quorum":
                    quorate = bool(item["quorate"]) if "quorate" in item else None
                elif kind == "master":
                    master = _clean(item, ("node", "status"))
                elif kind == "lrm":
                    lrm.append(_clean(item, ("node", "status")))
                elif kind == "service":
                    services.append(_clean(item, _SERVICE_KEYS))
            resources = [
                _clean(item, _RESOURCE_KEYS) for item in resource_items if isinstance(item, dict)
            ]
            payload = {
                "ha_configured": bool(services or resources),
                "quorate": quorate,
                "master": master,
                "lrm": lrm,
                "services": services,
                "resources": resources,
            }
            return self._format_response(payload)
        except Exception as e:
            self._handle_error("get HA status", e, privilege_key="get_ha_status")
