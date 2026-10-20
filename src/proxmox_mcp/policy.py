"""Call-time tool policy (SEC-01).

Risk classes come from ``ToolSpec.risk``. ``read_only`` blocks write, destructive and
exec tools and overrides the ``allow_*`` gates; ``allow_destructive`` / ``allow_exec``
gate their classes (default closed). Enforcement is a wrapper applied through
``register_tools(wrap=...)``: tools stay registered (the MCP surface is frozen) and a
denied call fails with ``policy_denied`` before any Proxmox call is made.
"""

import functools
import inspect
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastmcp.exceptions import ToolError
from mcp.types import TextContent as Content

from .validators import validate_node, validate_snapshot_name, validate_vmid

logger = logging.getLogger("proxmox-mcp.policy")

# risk class -> ordered config flags that block it (first match denies)
GATES: dict[str, tuple] = {
    "read": (),
    "write": ("read_only",),
    "destructive": ("read_only", "allow_destructive"),
    "exec": ("read_only", "allow_exec"),
}

_ENV = {
    "read_only": "PROXMOX_MCP_READ_ONLY",
    "allow_destructive": "PROXMOX_MCP_ALLOW_DESTRUCTIVE",
    "allow_exec": "PROXMOX_MCP_ALLOW_EXEC",
}
_CLI = {
    "read_only": "--read-only",
    "allow_destructive": "--allow-destructive",
    "allow_exec": "--allow-exec",
}


class PolicyDeniedError(ToolError):
    """Raised (as a ToolError) when the active policy forbids a tool call."""


@dataclass(frozen=True)
class Denial:
    """Why a call was denied and how an operator can change it."""

    flag: str
    kind: str  # "read_only" | "gate"
    config_key: str
    env_var: str
    cli_flag: str


class ToolPolicy:
    """Decides whether a tool (by risk class) may run under a ``PolicyConfig``."""

    def __init__(self, policy_config: Any):
        self._cfg = policy_config

    def check(self, spec: Any) -> Denial | None:
        for flag in GATES.get(spec.risk, ("read_only", "allow_destructive", "allow_exec")):
            value = bool(getattr(self._cfg, flag))
            blocked = value if flag == "read_only" else not value
            if blocked:
                return Denial(
                    flag=flag,
                    kind="read_only" if flag == "read_only" else "gate",
                    config_key=f"policy.{flag}",
                    env_var=_ENV[flag],
                    cli_flag=_CLI[flag],
                )
        return None

    def summary(self) -> dict[str, bool]:
        return {
            "read_only": bool(self._cfg.read_only),
            "allow_destructive": bool(self._cfg.allow_destructive),
            "allow_exec": bool(self._cfg.allow_exec),
        }


def _message(spec: Any, denial: Denial) -> str:
    if denial.kind == "read_only":
        why = "server is in read-only mode"
        how = (
            f"Set {denial.config_key}=false (or unset {denial.env_var} / omit "
            f"{denial.cli_flag}) and restart the server to allow it."
        )
    else:
        why = f"{spec.risk} tools are disabled by default"
        how = (
            f"Enable with {denial.config_key}=true, {denial.env_var}=true or "
            f"{denial.cli_flag} and restart the server."
        )
    return (
        f"policy_denied: tool '{spec.name}' (risk: {spec.risk}) is not allowed: {why} "
        f"[{denial.config_key}]. {how} No request was sent to Proxmox."
    )


def make_policy_wrap(policy: ToolPolicy) -> Callable[[Any, Callable[..., Any]], Callable[..., Any]]:
    """Return ``wrap(spec, handler)`` enforcing ``policy``; signature is preserved."""

    def wrap(spec: Any, handler: Callable[..., Any]) -> Callable[..., Any]:
        def _deny() -> None:
            denial = policy.check(spec)
            if denial is None:
                return
            # Tool name, risk and flag only: never log arguments.
            logger.warning(
                "policy denied tool=%s risk=%s flag=%s", spec.name, spec.risk, denial.flag
            )
            raise PolicyDeniedError(_message(spec, denial))

        if inspect.iscoroutinefunction(handler):

            @functools.wraps(handler)
            async def inner(*args: Any, **kwargs: Any) -> Any:
                _deny()
                return await handler(*args, **kwargs)

        else:

            @functools.wraps(handler)
            def inner(*args: Any, **kwargs: Any) -> Any:
                _deny()
                return handler(*args, **kwargs)

        return inner

    return wrap


def compose_wraps(*wraps: Callable[..., Any] | None) -> Callable[[Any, Callable[..., Any]], Any]:
    """Compose wraps; the first non-None wrap is outermost.

    ``compose_wraps(make_policy_wrap(p), user_wrap)`` therefore runs the policy check
    before any caller-supplied wrapper can execute.
    """
    active = [w for w in wraps if w is not None]

    def composed(spec: Any, handler: Callable[..., Any]) -> Callable[..., Any]:
        for w in reversed(active):
            handler = w(spec, handler)
        return handler

    return composed


_EFFECTS: dict[str, list[str]] = {
    "stop_vm": [
        "Hard power-off of the VM without a guest shutdown.",
        "Unsaved guest data may be lost and filesystems may need recovery.",
    ],
    "reset_vm": [
        "Hard reset of the VM, equivalent to pressing the reset button.",
        "Unsaved guest state is lost.",
    ],
    "delete_vm": [
        "Permanently removes the VM configuration, all its disks and all its snapshots.",
        "This cannot be undone.",
    ],
    "rollback_snapshot": [
        "Discards all current VM state since the snapshot was taken.",
        "Changes made after the snapshot cannot be recovered.",
    ],
    "stop_container": [
        "Hard stop of the container without a graceful shutdown.",
        "Processes are killed and unsaved data may be lost.",
    ],
    "delete_snapshot": [
        "Permanently removes the snapshot and the VM state it captured.",
        "It can no longer be rolled back to; this cannot be undone.",
    ],
}


# Tools whose node is resolved at execution time: the preview shows node null when omitted
# (only None counts as omitted; an empty string is still rejected by validate_node).
_NODE_OPTIONAL = frozenset({"stop_container"})


def build_preview(tool: str, **target: Any) -> list[Content]:
    """Return a confirmation preview for a destructive tool; performs no I/O.

    Inputs are validated (rejected, never sanitized) with the central validators first.
    """
    if tool not in _EFFECTS:
        raise ValueError(f"No preview defined for tool '{tool}'")
    shown: dict[str, Any] = {
        "node": (
            None
            if tool in _NODE_OPTIONAL and target.get("node") is None
            else validate_node(target.get("node"))
        ),
        "vmid": validate_vmid(target.get("vmid")),
    }
    if "name" in target:
        shown["name"] = validate_snapshot_name(target["name"])
    effects = list(_EFFECTS[tool])
    if tool == "delete_vm":
        force = bool(target.get("force", False))
        shown["force"] = force
        if force:
            effects.append("A running VM will be stopped first (force=true).")
    payload = {
        "preview": True,
        "executed": False,
        "tool": tool,
        "target": shown,
        "effects": effects,
        "how_to_confirm": f"Repeat the {tool} call with confirm=true to perform this operation.",
        "note": (
            "This preview only echoes the target you supplied (no lookup is made, so verify "
            "node, vmid and name yourself). confirm=true is a safeguard against accidents, "
            "not an authorization: the operation is permitted only when the server runs "
            "with policy.allow_destructive enabled."
        ),
    }
    return [Content(type="text", text=json.dumps(payload))]
