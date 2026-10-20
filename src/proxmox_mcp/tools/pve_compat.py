"""PVE 8.x / 9.x API compatibility helpers.

Existence of a VM is never decided by matching error text. Proxmox answers a missing VM
with HTTP 500 ("Configuration file ... does not exist"), so a status code alone is not
enough either: ``require_vm_status`` confirms absence with a deterministic
``GET nodes/{node}/qemu`` listing. Error TEXT is consulted in exactly one place, the
``KNOWN_500_MARKERS`` table below, and only to classify HTTP 500 bodies that PVE uses for
permission, lock and guest-agent failures. It is never used to decide that a VM is missing.

This module must not import from tools/vm.py or tools/console/manager.py (both import it).
"""
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests
from proxmoxer.core import ResourceException

from ..utils.redaction import redact
from ..validators import InputValidationError, validate_upid

# (privilege text, ACL path template) per operation key; PVE admin guide (pveum) privileges.
OPERATION_PRIVILEGES: dict[str, tuple[str, str]] = {
    "start_vm": ("VM.PowerMgmt", "/vms/{vmid}"),
    "stop_vm": ("VM.PowerMgmt", "/vms/{vmid}"),
    "shutdown_vm": ("VM.PowerMgmt", "/vms/{vmid}"),
    "reset_vm": ("VM.PowerMgmt", "/vms/{vmid}"),
    "delete_vm": ("VM.Allocate", "/vms/{vmid}"),
    "create_vm": (
        "VM.Allocate (and Datastore.AllocateSpace on /storage/<id>)",
        "/vms/{vmid}",
    ),
    "create_snapshot": ("VM.Snapshot", "/vms/{vmid}"),
    "rollback_snapshot": ("VM.Snapshot.Rollback", "/vms/{vmid}"),
    "update_vm": ("VM.Config.CPU / VM.Config.Memory / VM.Config.Options", "/vms/{vmid}"),
    "get_vm_usage": ("VM.Audit", "/vms/{vmid}"),
    "get_vms": ("VM.Audit", "/vms/<vmid>"),
    "get_storage": ("Datastore.Audit", "/storage"),
    "get_node_status": ("Sys.Audit", "/nodes/{node}"),
    "get_nodes": ("Sys.Audit", "/nodes"),
    "get_containers": ("Sys.Audit", "/"),
    "get_cluster_status": ("Sys.Audit", "/"),
    "start_container": ("VM.PowerMgmt", "/vms/{vmid}"),
    "stop_container": ("VM.PowerMgmt", "/vms/{vmid}"),
    "shutdown_container": ("VM.PowerMgmt", "/vms/{vmid}"),
    "list_snapshots": ("VM.Audit", "/vms/{vmid}"),
    "delete_snapshot": ("VM.Snapshot", "/vms/{vmid}"),
    "list_backups": ("Datastore.Audit", "/storage/<storage>"),
    "get_ha_status": ("Sys.Audit", "/"),
    "get_task_status": ("Sys.Audit (or ownership of the task)", "/nodes/{node}"),
    "wait_for_task": ("Sys.Audit (or ownership of the task)", "/nodes/{node}"),
    "execute_vm_command": (
        "VM.GuestAgent.Unrestricted (PVE 9) or VM.Monitor (PVE 8)",
        "/vms/{vmid}",
    ),
}

# The ONLY place error text is consulted: classification of HTTP 500 bodies (case-insensitive).
KNOWN_500_MARKERS: dict[str, tuple[str, ...]] = {
    "permission": ("permission check failed",),
    "lock": ("can't lock file", "cannot lock", "is locked", "got lock timeout"),
    "agent": ("guest agent is not running", "qga is not running"),
}

class TaskFailedError(RuntimeError):
    """A waited-for Proxmox task stopped without exitstatus OK (message names UPID/exitstatus)."""


def is_upid(value: Any) -> bool:
    """True for a well-formed PVE task id (delegates to ``validators.validate_upid``)."""
    try:
        validate_upid(value)
    except InputValidationError:
        return False
    return True


def _status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _body(exc: BaseException) -> str:
    return str(exc).lower()


def _has_marker(exc: BaseException, kind: str) -> bool:
    if _status_code(exc) != 500:
        return False
    text = _body(exc)
    return any(m in text for m in KNOWN_500_MARKERS[kind])


def is_permission_failure(exc: BaseException) -> bool:
    """HTTP 403, or PVE's 500 'Permission check failed'."""
    return _status_code(exc) == 403 or _has_marker(exc, "permission")


def is_lock_conflict(exc: BaseException) -> bool:
    return _has_marker(exc, "lock")


def is_agent_not_running(exc: BaseException) -> bool:
    return _has_marker(exc, "agent")


def _privilege_text(key: str, node: str | None, vmid: str | None) -> str | None:
    if key not in OPERATION_PRIVILEGES:
        return None
    priv, path = OPERATION_PRIVILEGES[key]
    path = path.replace("{vmid}", str(vmid) if vmid is not None else "<vmid>")
    path = path.replace("{node}", str(node) if node is not None else "<node>")
    return f"{priv} on {path}"


def translate_pve_error(
    exc: BaseException,
    operation: str,
    *,
    node: str | None = None,
    vmid: str | None = None,
    major: int | None = None,
    privilege_key: str | None = None,
) -> Exception:
    """Map a proxmoxer / connection error to an actionable exception (caller raises it).

    Decision order is the HTTP status code; see the module docstring for the 500 markers.
    Messages are fixed templates plus operation/vmid/node/privilege, and the generic
    fallback passes the original text through ``redact``.
    """
    key = privilege_key or operation
    code = _status_code(exc)
    if isinstance(exc, ResourceException) or code is not None:
        if code == 401:
            return RuntimeError(
                f"Authentication failed while trying to {operation}: check the API token "
                "user, token name and value."
            )
        if is_permission_failure(exc):
            if key == "execute_vm_command" and vmid is not None:
                return ValueError(guest_agent_privilege_message(vmid, major))
            needed = _privilege_text(key, node, vmid)
            hint = f" Required privilege: {needed}." if needed else ""
            return ValueError(
                f"Permission denied: the API token may not {operation}.{hint} "
                "Grant the privilege to the token (and its user) with pveum acl modify."
            )
        if code == 404:
            return ValueError(f"Resource not found while trying to {operation}.")
        if is_lock_conflict(exc):
            return RuntimeError(
                f"Cannot {operation}: the VM is locked by another task (backup, migration, "
                "snapshot or clone). Wait for it to finish and retry."
            )
        if code in (595, 596):
            return RuntimeError(
                f"Cannot {operation}: the Proxmox node is unreachable (HTTP {code}). "
                "Check that the node is online and part of the cluster."
            )
    elif isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return RuntimeError(
            f"Cannot {operation}: the Proxmox host is unreachable or timed out. "
            "Check host, port and network."
        )
    return RuntimeError(f"Failed to {operation}: {redact(str(exc))}")


def vm_listed(api: Any, node: str, vmid: Any) -> bool:
    """Deterministic existence check: is ``vmid`` in ``GET nodes/{node}/qemu``?"""
    listing = api.nodes(node).qemu.get()
    if not isinstance(listing, (list, tuple)):
        return False
    return any(isinstance(item, dict) and str(item.get("vmid")) == str(vmid) for item in listing)


def require_vm_status(api: Any, node: str, vmid: Any, operation: str) -> dict[str, Any]:
    """Return ``status/current`` of the VM or raise a precise error.

    403 -> permission error; 404 -> not found; 500 -> not found only when the VM is absent
    from the qemu listing (never from the error text); anything else is translated.
    """
    try:
        return api.nodes(node).qemu(vmid).status.current.get()
    except ResourceException as exc:
        code = _status_code(exc)
        if code == 404:
            raise ValueError(f"VM {vmid} not found on node {node}") from None
        if code == 500 and not is_permission_failure(exc) and not is_lock_conflict(exc):
            try:
                listed = vm_listed(api, node, vmid)
            except Exception:
                raise translate_pve_error(
                    exc, operation, node=node, vmid=vmid
                ) from None
            if not listed:
                raise ValueError(f"VM {vmid} not found on node {node}") from None
        raise translate_pve_error(exc, operation, node=node, vmid=vmid) from None


def describe_task_result(result: Any) -> str:
    """Render the return value of an async PVE call (UPID string, None on 9.1+ null returns)."""
    if result is None:
        return "Task: no task id returned (PVE may complete this synchronously); verify VM state"
    if isinstance(result, str):
        return f"Task ID: {result[:200]}" if result else (
            "Task: no task id returned (empty); verify VM state"
        )
    text = repr(result)
    return f"Task result: {text[:200]}"


@dataclass(frozen=True)
class PveVersion:
    version: str
    release: str | None
    major: int
    minor: int


def parse_pve_version(payload: Any) -> PveVersion | None:
    """Parse ``GET /version``; never raises, None for anything unexpected."""
    if not isinstance(payload, dict):
        return None
    version = payload.get("version")
    if not isinstance(version, str):
        return None
    m = re.match(r"^(\d+)(?:\.(\d+))?", version)
    if not m:
        return None
    release = payload.get("release")
    return PveVersion(
        version=version,
        release=release if isinstance(release, str) else None,
        major=int(m.group(1)),
        minor=int(m.group(2) or 0),
    )


def guest_agent_privilege_message(vmid: Any, major: int | None) -> str:
    """Version-aware permission hint for ``agent/exec`` (built from vmid and version only)."""
    base = f"Permission denied: the API token may not run guest-agent commands on VM {vmid} "
    path = f"(ACL path /vms/{vmid}). "
    if major is not None and major >= 9:
        return (
            base + path + "On PVE 9 VM.Monitor was removed; grant "
            "VM.GuestAgent.Unrestricted (expected for exec, unverified; the other "
            "VM.GuestAgent.* privileges cover audit, file read/write and freeze/trim)."
        )
    if major is not None:
        return base + path + "On PVE 8 this requires the VM.Monitor privilege."
    return (
        base + path + "PVE 8 requires VM.Monitor; PVE 9 removed it and uses "
        "VM.GuestAgent.Unrestricted (expected for exec, unverified)."
    )


def wait_task_stopped(
    api: Any,
    node: str,
    upid: str,
    timeout: float = 30.0,
    interval: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Poll a task until it stops; only exitstatus OK is success (WARNINGS is not).

    Bounded by a monotonic deadline. An invalid UPID raises before any API call.
    """
    if not is_upid(upid):
        raise ValueError("invalid task id (UPID)")
    deadline = clock() + timeout
    while True:
        status = api.nodes(node).tasks(upid).status.get()
        if isinstance(status, dict) and status.get("status") == "stopped":
            exitstatus = status.get("exitstatus")
            if exitstatus == "OK":
                return status
            raise RuntimeError(
                f"Task did not finish successfully (exitstatus: {redact(str(exitstatus))})"
            )
        if clock() >= deadline:
            raise RuntimeError(f"Timed out after {timeout:g}s waiting for task to stop")
        sleep(interval)
