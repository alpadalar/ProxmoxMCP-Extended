# ruff: noqa: E501  (Annotated parameter descriptions are kept verbatim from the original servers)
"""Single tool registry shared by the stdio and HTTP transports.

``build_registry(ctx)`` returns the ordered list of :class:`ToolSpec` (the MCP
tool surface, see tests/golden/tools.json); ``register_tools(mcp, specs, wrap=None)`` registers them on a
FastMCP instance.  Phase 4 attaches policy gates through ``wrap`` (called as
``wrap(spec, handler) -> handler`` and required to preserve the signature, e.g. with
``functools.wraps``, so ``tests/golden/tools.json`` stays valid) and MCP annotations
(readOnlyHint/destructiveHint) through ``ToolSpec.annotations``.
"""
import json
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, Dict, FrozenSet, List, Optional

from fastmcp import FastMCP
from mcp.types import TextContent as Content
from pydantic import Field

from ..policy import build_preview
from .definitions import (
    CREATE_SNAPSHOT_DESC,
    CREATE_VM_DESC,
    DELETE_SNAPSHOT_DESC,
    DELETE_VM_DESC,
    EXECUTE_VM_COMMAND_DESC,
    GET_CLUSTER_STATUS_DESC,
    GET_CONTAINERS_DESC,
    GET_NODE_STATUS_DESC,
    GET_NODES_DESC,
    GET_STORAGE_DESC,
    GET_TASK_STATUS_DESC,
    GET_VM_USAGE_DESC,
    GET_VMS_DESC,
    HEALTH_DESC,
    LIST_SNAPSHOTS_DESC,
    RESET_VM_DESC,
    ROLLBACK_SNAPSHOT_DESC,
    SHUTDOWN_VM_DESC,
    START_VM_DESC,
    STOP_VM_DESC,
    UPDATE_VM_DESC,
    WAIT_FOR_TASK_DESC,
)

WaitParam = Annotated[bool, Field(description="Wait for the Proxmox task to finish before returning (default: false); a failed task raises an error, a task with warnings is reported as such", default=False)]
TimeoutParam = Annotated[int, Field(description="Seconds to wait when wait=true (1-300, default 30); timing out reports the task as still running, not as a failure", ge=1, le=300, default=30)]

RISK_CLASSES = {
    "read": (
        "get_nodes", "get_node_status", "get_vms", "get_containers", "get_storage",
        "get_cluster_status", "get_vm_usage", "health", "get_task_status", "wait_for_task",
        "list_snapshots",
    ),
    "write": ("create_vm", "start_vm", "shutdown_vm", "create_snapshot"),
    # update_vm overwrites existing configuration (memory, cores, name), so it is gated by
    # allow_destructive, matching its destructiveHint annotation.
    "destructive": ("stop_vm", "reset_vm", "delete_vm", "rollback_snapshot", "update_vm",
                    "delete_snapshot"),
    "exec": ("execute_vm_command",),
}
_RISK_BY_NAME = {n: r for r, names in RISK_CLASSES.items() for n in names}

# MCP tool annotations (camelCase keys, accepted by fastmcp 4.x as a dict).
_ANNOTATION_DEFAULTS: Dict[str, Dict[str, bool]] = {
    "read": {
        "readOnlyHint": True, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    },
    "write": {
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": False, "openWorldHint": False,
    },
    "destructive": {
        "readOnlyHint": False, "destructiveHint": True,
        "idempotentHint": False, "openWorldHint": False,
    },
    "exec": {
        "readOnlyHint": False, "destructiveHint": True,
        "idempotentHint": False, "openWorldHint": False,
    },
}
ANNOTATION_OVERRIDES: Dict[str, Dict[str, bool]] = {
    "start_vm": {"idempotentHint": True},
    "shutdown_vm": {"idempotentHint": True},
    "execute_vm_command": {"openWorldHint": True},  # runs arbitrary code in a guest
}


def annotations_for(name: str, risk: str) -> Dict[str, bool]:
    """MCP annotations for tool ``name`` derived from its risk class."""
    annotations = dict(_ANNOTATION_DEFAULTS[risk])
    annotations.update(ANNOTATION_OVERRIDES.get(name, {}))
    return annotations


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool: name, handler, description and policy metadata."""

    name: str
    handler: Callable[..., Any]
    description: str
    annotations: Optional[Dict[str, Any]] = None
    risk: str = ""  # required: must be one of RISK_CLASSES (checked in __post_init__)
    tags: FrozenSet[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        # Fail closed: a tool without an explicit, known risk class is never constructed,
        # so it can not slip through the policy gates as an implicit "read" tool.
        if self.risk not in RISK_CLASSES:
            raise ValueError(
                f"ToolSpec '{self.name}' needs an explicit risk class "
                f"({', '.join(RISK_CLASSES)}); got {self.risk!r}"
            )


@dataclass
class ToolContext:
    """Dependencies the tool handlers close over."""

    node_tools: Any
    vm_tools: Any
    storage_tools: Any
    cluster_tools: Any
    health_payload: Callable[[], dict]
    task_tools: Any = None


def build_registry(ctx: ToolContext) -> List[ToolSpec]:
    """Build the tool specs bound to ``ctx``."""
    specs: List[ToolSpec] = []

    def _tool(description: str):
        def deco(fn):
            specs.append(
                ToolSpec(
                    name=fn.__name__,
                    handler=fn,
                    description=description,
                    annotations=annotations_for(fn.__name__, _RISK_BY_NAME[fn.__name__]),
                    risk=_RISK_BY_NAME[fn.__name__],
                )
            )
            return fn

        return deco

    # Node tools
    @_tool(GET_NODES_DESC)
    def get_nodes():
        return ctx.node_tools.get_nodes()

    @_tool(GET_NODE_STATUS_DESC)
    def get_node_status(
        node: Annotated[str, Field(description="Name/ID of node to query (e.g. 'pve1', 'proxmox-node2')")]
    ):
        return ctx.node_tools.get_node_status(node)

    # VM tools
    @_tool(GET_VMS_DESC)
    def get_vms():
        return ctx.vm_tools.get_vms()

    @_tool(GET_CONTAINERS_DESC)
    def get_containers():
        result = ctx.cluster_tools.list_containers()
        return [Content(type="text", text=json.dumps(result))]

    @_tool(CREATE_VM_DESC)
    def create_vm(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="New VM ID number (e.g. '200', '300')")],
        name: Annotated[str, Field(description="VM name (e.g. 'my-new-vm', 'web-server')")],
        cpus: Annotated[int, Field(description="Number of CPU cores (e.g. 1, 2, 4)", ge=1, le=32)],
        memory: Annotated[int, Field(description="Memory size in MB (e.g. 2048 for 2GB)", ge=512, le=131072)],
        disk_size: Annotated[int, Field(description="Disk size in GB (e.g. 10, 20, 50)", ge=5, le=1000)],
        storage: Annotated[Optional[str], Field(description="Storage name (optional, will auto-detect)", default=None)] = None,
        ostype: Annotated[Optional[str], Field(description="OS type (optional, default: 'l26' for Linux)", default=None)] = None,
        iso_name: Annotated[Optional[str], Field(description="ISO file name to mount (optional)", default=None)] = None,
        iso_storage: Annotated[Optional[str], Field(description="Storage containing the ISO (optional)", default=None)] = None,
    ):
        return ctx.vm_tools.create_vm(node, vmid, name, cpus, memory, disk_size, storage, ostype, iso_name, iso_storage)

    @_tool(EXECUTE_VM_COMMAND_DESC)
    async def execute_vm_command(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve1', 'proxmox-node2')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '100', '101')")],
        command: Annotated[str, Field(description="Shell command to run (e.g. 'uname -a', 'systemctl status nginx')")],
        args: Annotated[Optional[List[str]], Field(description="Optional argument list. When given, the command is the program and args its arguments (no shell is involved). When omitted, command is split into words with shlex rules (no shell).", default=None)] = None,
    ):
        return await ctx.vm_tools.execute_command(node, vmid, command, args)

    # VM Power Management tools
    @_tool(START_VM_DESC)
    def start_vm(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '101')")],
        wait: WaitParam = False,
        timeout: TimeoutParam = 30,
    ):
        return ctx.vm_tools.start_vm(node, vmid, wait, timeout)

    @_tool(STOP_VM_DESC)
    def stop_vm(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '101')")],
        confirm: Annotated[bool, Field(description="Set true to actually perform this destructive operation. When omitted or false only a preview is returned and nothing is changed.", default=False)] = False,
        wait: WaitParam = False,
        timeout: TimeoutParam = 30,
    ):
        if not confirm:
            return build_preview("stop_vm", node=node, vmid=vmid)
        return ctx.vm_tools.stop_vm(node, vmid, wait, timeout)

    @_tool(SHUTDOWN_VM_DESC)
    def shutdown_vm(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '101')")],
        wait: WaitParam = False,
        timeout: TimeoutParam = 30,
    ):
        return ctx.vm_tools.shutdown_vm(node, vmid, wait, timeout)

    @_tool(RESET_VM_DESC)
    def reset_vm(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '101')")],
        confirm: Annotated[bool, Field(description="Set true to actually perform this destructive operation. When omitted or false only a preview is returned and nothing is changed.", default=False)] = False,
        wait: WaitParam = False,
        timeout: TimeoutParam = 30,
    ):
        if not confirm:
            return build_preview("reset_vm", node=node, vmid=vmid)
        return ctx.vm_tools.reset_vm(node, vmid, wait, timeout)

    @_tool(DELETE_VM_DESC)
    def delete_vm(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '998')")],
        force: Annotated[bool, Field(description="Force deletion even if VM is running", default=False)] = False,
        confirm: Annotated[bool, Field(description="Set true to actually perform this destructive operation. When omitted or false only a preview is returned and nothing is changed.", default=False)] = False,
        wait: WaitParam = False,
        timeout: TimeoutParam = 30,
    ):
        if not confirm:
            return build_preview("delete_vm", node=node, vmid=vmid, force=force)
        return ctx.vm_tools.delete_vm(node, vmid, force, wait, timeout)

    @_tool(UPDATE_VM_DESC)
    def update_vm(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '100')")],
        memory: Annotated[Optional[int], Field(description="New memory size in MB (e.g. 4096 for 4GB, 6144 for 6GB)", default=None)] = None,
        cpus: Annotated[Optional[int], Field(description="New number of CPU cores (e.g. 1, 2, 4)", default=None)] = None,
        name: Annotated[Optional[str], Field(description="New VM name", default=None)] = None,
    ):
        return ctx.vm_tools.update_vm(node, vmid, memory, cpus, name)

    # VM snapshot tools
    @_tool(CREATE_SNAPSHOT_DESC)
    def create_snapshot(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '100')")],
        name: Annotated[str, Field(description="Snapshot name (e.g. 'pre-upgrade')")],
        description: Annotated[Optional[str], Field(description="Optional description", default=None)] = None,
        vmstate: Annotated[bool, Field(description="Include VM memory state", default=False)] = False,
        wait: WaitParam = False,
        timeout: TimeoutParam = 30,
    ):
        return ctx.vm_tools.create_snapshot(node, vmid, name, description, vmstate, wait, timeout)

    @_tool(ROLLBACK_SNAPSHOT_DESC)
    def rollback_snapshot(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '100')")],
        name: Annotated[str, Field(description="Snapshot name to rollback to")],
        confirm: Annotated[bool, Field(description="Set true to actually perform this destructive operation. When omitted or false only a preview is returned and nothing is changed.", default=False)] = False,
        wait: WaitParam = False,
        timeout: TimeoutParam = 30,
    ):
        if not confirm:
            return build_preview("rollback_snapshot", node=node, vmid=vmid, name=name)
        return ctx.vm_tools.rollback_snapshot(node, vmid, name, wait, timeout)

    @_tool(LIST_SNAPSHOTS_DESC)
    def list_snapshots(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '100')")],
    ):
        return ctx.vm_tools.list_snapshots(node, vmid)

    @_tool(DELETE_SNAPSHOT_DESC)
    def delete_snapshot(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '100')")],
        name: Annotated[str, Field(description="Snapshot name to delete")],
        confirm: Annotated[bool, Field(description="Set true to actually perform this destructive operation. When omitted or false only a preview is returned and nothing is changed.", default=False)] = False,
        wait: WaitParam = False,
        timeout: TimeoutParam = 30,
    ):
        if not confirm:
            return build_preview("delete_snapshot", node=node, vmid=vmid, name=name)
        return ctx.vm_tools.delete_snapshot(node, vmid, name, wait, timeout)

    # VM usage tool
    @_tool(GET_VM_USAGE_DESC)
    def get_vm_usage(
        node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
        vmid: Annotated[str, Field(description="VM ID number (e.g. '100')")],
    ):
        return ctx.vm_tools.get_vm_usage(node, vmid)

    # Storage tools
    @_tool(GET_STORAGE_DESC)
    def get_storage():
        return ctx.storage_tools.get_storage()

    # Cluster tools
    @_tool(GET_CLUSTER_STATUS_DESC)
    def get_cluster_status():
        return ctx.cluster_tools.get_cluster_status()

    # Task tools
    @_tool(GET_TASK_STATUS_DESC)
    def get_task_status(
        upid: Annotated[str, Field(description="Task id (UPID) returned by a mutating tool")],
    ):
        return ctx.task_tools.get_task_status(upid)

    @_tool(WAIT_FOR_TASK_DESC)
    def wait_for_task(
        upid: Annotated[str, Field(description="Task id (UPID) returned by a mutating tool")],
        timeout: Annotated[int, Field(description="Maximum seconds to wait (1-300, default 30); a still-running task is reported as running, not as an error", ge=1, le=300, default=30)] = 30,
    ):
        return ctx.task_tools.wait_for_task(upid, timeout)

    # System tools
    @_tool(HEALTH_DESC)
    def health():
        return [Content(type="text", text=json.dumps(ctx.health_payload()))]

    return specs


def register_tools(
    mcp: FastMCP,
    specs: List[ToolSpec],
    wrap: Optional[Callable[[ToolSpec, Callable[..., Any]], Callable[..., Any]]] = None,
) -> None:
    """Register ``specs`` on ``mcp`` (optionally wrapping each handler)."""
    names = [spec.name for spec in specs]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"Duplicate tool names: {duplicates}")
    for spec in specs:
        handler = wrap(spec, spec.handler) if wrap is not None else spec.handler
        mcp.tool(
            handler,
            name=spec.name,
            description=spec.description,
            annotations=spec.annotations,
        )
