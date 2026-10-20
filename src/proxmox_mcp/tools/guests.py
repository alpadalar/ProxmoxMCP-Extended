"""Guest resolver: finds node and type of a guest (QEMU VM or LXC container) by vmid.

The lookup goes to ``cluster/resources`` on EVERY call and is never cached, because guests
migrate between nodes. Node and type used for API paths therefore come from the cluster, not
from raw tool input.
"""

from dataclasses import dataclass
from typing import Any

from ..validators import validate_node, validate_vmid


@dataclass(frozen=True)
class Guest:
    """A guest as reported by ``cluster/resources``."""

    node: str
    vmid: str
    type: str  # "qemu" | "lxc"
    status: str | None
    name: str | None
    template: bool


_KIND = {"qemu": "a qemu VM", "lxc": "an LXC container"}


def resolve_guest(
    api: Any, vmid: Any, expected_type: str | None = None, node: str | None = None
) -> Guest:
    """Resolve ``vmid`` through ``cluster/resources`` (uncached); raise ValueError if unusable."""
    vmid = validate_vmid(vmid)
    node = None if node is None else validate_node(node)
    resources = api.cluster.resources.get(type="vm") or []
    item = next(
        (
            r
            for r in resources
            if isinstance(r, dict) and r.get("type") in _KIND and str(r.get("vmid")) == vmid
        ),
        None,
    )
    if item is None:
        raise ValueError(
            f"Guest {vmid} not found in cluster resources "
            f"(the token may lack VM.Audit on /vms/{vmid})"
        )
    gtype = item["type"]
    if expected_type is not None and gtype != expected_type:
        if expected_type == "lxc":
            raise ValueError(
                f"Guest {vmid} is a qemu VM, not an LXC container; use start_vm/stop_vm/shutdown_vm"
            )
        raise ValueError(f"Guest {vmid} is an LXC container, not a qemu VM")
    resolved_node = validate_node(item.get("node"))
    if node is not None and node != resolved_node:
        raise ValueError(f"Guest {vmid} runs on node {resolved_node}, not on node {node}")
    template = bool(item.get("template"))
    if template:
        raise ValueError(f"Guest {vmid} is a template and cannot be started or stopped")
    return Guest(
        node=resolved_node,
        vmid=vmid,
        type=gtype,
        status=item.get("status"),
        name=item.get("name"),
        template=template,
    )
