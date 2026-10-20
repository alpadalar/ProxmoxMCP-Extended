"""LXC container power tools (start, stop, shutdown), addressed by vmid.

Node and type come from :func:`resolve_guest` on every call. Mutating calls return the task
id (UPID) and support the optional ``wait`` / ``timeout`` semantics of the VM tools.
"""

import time
from typing import Any

from mcp.types import TextContent as Content

from ..validators import validate_node, validate_optional, validate_vmid, validate_wait_timeout
from .base import ProxmoxTool
from .guests import resolve_guest
from .tasks import task_result_text


class ContainerTools(ProxmoxTool):
    """Power management for LXC containers."""

    def __init__(self, proxmox_api: Any) -> None:
        super().__init__(proxmox_api)
        self._sleep = time.sleep
        self._clock = time.monotonic

    def _task_text(self, task_result: Any, wait: bool, timeout: int) -> str:
        return task_result_text(
            self.proxmox, task_result, wait, timeout, sleep=self._sleep, clock=self._clock
        )

    def _run(
        self,
        op: str,
        vmid: Any,
        node: Any,
        wait: bool,
        timeout: int,
        skip_state: str,
        skip_text: str,
        action: str,
        text: str,
    ) -> list[Content]:
        """Shared flow: validate, resolve (lxc), read status, issue ``action`` unless skipped."""
        vmid = validate_vmid(vmid)
        node = validate_optional(validate_node, node)
        validate_wait_timeout(timeout)
        resolved = None
        try:
            resolved = resolve_guest(self.proxmox, vmid, expected_type="lxc", node=node)
            lxc = self.proxmox.nodes(resolved.node).lxc(vmid)
            current = lxc.status.current.get().get("status")
            if current == skip_state:
                return [Content(type="text", text=skip_text.format(vmid=vmid))]
            task_result = getattr(lxc.status, action).post()
            message = f"{text.format(vmid=vmid)}\n🔧 {self._task_text(task_result, wait, timeout)}"
            return [Content(type="text", text=message)]
        except Exception as e:
            self._handle_error(
                f"{op} container {vmid}",
                e,
                privilege_key=f"{op}_container",
                node=resolved.node if resolved else node,
                vmid=vmid,
            )

    def start_container(
        self, vmid: str, node: str | None = None, wait: bool = False, timeout: int = 30
    ) -> list[Content]:
        """Start an LXC container."""
        return self._run(
            "start",
            vmid,
            node,
            wait,
            timeout,
            "running",
            "🟢 Container {vmid} is already running",
            "start",
            "🚀 Container {vmid} start initiated successfully",
        )

    def stop_container(
        self, vmid: str, node: str | None = None, wait: bool = False, timeout: int = 30
    ) -> list[Content]:
        """Hard-stop an LXC container (the caller enforces confirm)."""
        return self._run(
            "stop",
            vmid,
            node,
            wait,
            timeout,
            "stopped",
            "🔴 Container {vmid} is already stopped",
            "stop",
            "🛑 Container {vmid} stop initiated successfully",
        )

    def shutdown_container(
        self, vmid: str, node: str | None = None, wait: bool = False, timeout: int = 30
    ) -> list[Content]:
        """Gracefully shut down an LXC container (no PVE-side timeout is sent)."""
        return self._run(
            "shutdown",
            vmid,
            node,
            wait,
            timeout,
            "stopped",
            "🔴 Container {vmid} is already stopped",
            "shutdown",
            "💤 Container {vmid} graceful shutdown initiated",
        )
