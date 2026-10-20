"""
Module for managing VM console operations.

This module provides functionality for interacting with VM consoles:
- Executing commands within VMs via QEMU guest agent
- Handling command execution lifecycle
- Managing command output and status
- Error handling and logging

The module implements a robust command execution system with:
- VM state verification
- Asynchronous command execution
- Detailed status tracking
- Comprehensive error handling
"""

import asyncio
import logging
import shlex
import time
from collections.abc import Callable
from functools import partial
from typing import Any

import requests
from proxmoxer.core import ResourceException

from ...utils.redaction import redact_local
from ..pve_compat import (
    guest_agent_privilege_message,
    is_agent_not_running,
    is_permission_failure,
    require_vm_status,
    translate_pve_error,
)


class VMConsoleManager:
    """Manager class for VM console operations.

    Provides functionality for:
    - Executing commands in VM consoles
    - Managing command execution lifecycle
    - Handling command output and errors
    - Monitoring execution status

    Uses QEMU guest agent for reliable command execution with:
    - VM state verification before execution
    - Asynchronous command processing
    - Detailed output capture
    - Comprehensive error handling
    """

    MAX_ARGV_ITEMS = 64
    MAX_ARG_CHARS = 4096
    MAX_ARGV_TOTAL_CHARS = 32768
    POLL_START = 0.5
    POLL_MAX = 2.0

    def __init__(
        self,
        proxmox_api: Any,
        exec_timeout: float = 30.0,
        exec_max_output: int = 65536,
        exec_max_concurrent: int = 2,
        pve_major: Callable[[], int | None] = lambda: None,
    ):
        """Initialize the VM console manager.

        Args:
            proxmox_api: Initialized ProxmoxAPI instance
            exec_timeout: Maximum seconds to wait for a command to exit
            exec_max_output: Maximum bytes kept per output stream (stdout / stderr)
            exec_max_concurrent: Maximum commands started and polled concurrently (the
                rest wait for a slot); keeps polling from filling the worker thread pool
            pve_major: Returns the PVE major version (or None) for privilege hints
        """
        self.proxmox = proxmox_api
        self.exec_timeout = exec_timeout
        self.exec_max_output = exec_max_output
        self.exec_max_concurrent = max(1, int(exec_max_concurrent))
        self._exec_slots = asyncio.Semaphore(self.exec_max_concurrent)
        self._pve_major = pve_major
        self.logger = logging.getLogger("proxmox-mcp.vm-console")

    def _raise_agent_hint(self, exc: BaseException, vmid: str) -> None:
        """Raise a precise ValueError for guest-agent permission / availability failures.

        The messages are built from vmid and the PVE version only (never the command).
        """
        if is_permission_failure(exc):
            raise ValueError(guest_agent_privilege_message(vmid, self._pve_major())) from None
        if is_agent_not_running(exc):
            raise ValueError(
                f"The QEMU guest agent is not running in VM {vmid}. Set `agent: 1` on the VM "
                "and install and start qemu-guest-agent inside the guest."
            ) from None

    def _raise_translated(
        self, exc: BaseException, node: str, vmid: str, command: str, argv: list[str]
    ) -> None:
        """Raise the status-code based translation for PVE / connection errors (else return).

        The translated exception is marked so the outer handlers pass it through unchanged;
        its text is scrubbed of the command per call.
        """
        if not isinstance(exc, (ResourceException, requests.exceptions.RequestException)):
            return
        translated = translate_pve_error(
            exc,
            "execute command on VM",
            node=node,
            vmid=vmid,
            major=self._pve_major(),
            privilege_key="execute_vm_command",
        )
        clean = type(translated)(redact_local(str(translated), command, *argv))
        clean._pve_translated = True  # type: ignore[attr-defined]
        raise clean from None

    @classmethod
    def _build_argv(cls, command: str, args: list[str] | None = None) -> list[str]:
        """Build and validate the argv list sent to the guest agent (no shell).

        With ``args`` the command is the program and ``args`` its arguments; otherwise the
        command string is split into words with shlex rules. Oversized or malformed input is
        rejected, never truncated. Error messages never contain the command text.
        """
        if not isinstance(command, str):
            raise ValueError("command must be a string")
        if args is None:
            try:
                argv = shlex.split(command)
            except ValueError:
                raise ValueError(
                    "command could not be parsed (unbalanced quotes); use args to pass "
                    "arguments explicitly"
                ) from None
        else:
            if not isinstance(args, (list, tuple)):
                raise ValueError("args must be a list of strings")
            argv = [command, *args]
        if not argv or not argv[0]:
            raise ValueError("command must not be empty")
        if len(argv) > cls.MAX_ARGV_ITEMS:
            raise ValueError(f"too many arguments (maximum {cls.MAX_ARGV_ITEMS} including program)")
        total = 0
        for index, item in enumerate(argv):
            if not isinstance(item, str):
                raise ValueError(f"argument {index} must be a string")
            if "\x00" in item:
                raise ValueError(f"argument {index} contains a NUL byte")
            if len(item) > cls.MAX_ARG_CHARS:
                raise ValueError(
                    f"argument {index} is too long (maximum {cls.MAX_ARG_CHARS} characters)"
                )
            total += len(item)
        if total > cls.MAX_ARGV_TOTAL_CHARS:
            raise ValueError(
                f"arguments are too long in total (maximum {cls.MAX_ARGV_TOTAL_CHARS} characters)"
            )
        return argv

    def _cap(self, text: Any) -> "tuple[str, bool]":
        """Cap ``text`` at ``exec_max_output`` UTF-8 bytes on a character boundary."""
        text = text if isinstance(text, str) else str(text)
        raw = text.encode("utf-8", errors="replace")
        if len(raw) <= self.exec_max_output:
            return text, False
        kept = raw[: self.exec_max_output].decode("utf-8", errors="ignore")
        return f"{kept}\n[output truncated at {self.exec_max_output} bytes]", True

    async def execute_command(
        self,
        node: str,
        vmid: str,
        command: str,
        args: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a command in a VM via the guest agent, at most N at a time.

        At most ``exec_max_concurrent`` commands run through the start/poll cycle at once;
        further calls wait for a slot (input is validated first, before waiting).

        Best effort only: the guest agent has no kill endpoint. When the MCP wait limit
        passes, or the call is cancelled, the process is abandoned and keeps running in the
        guest; its exec-status entry stays in the agent until polled.
        """
        self._build_argv(command, args)  # reject bad input without taking a slot
        async with self._exec_slots:
            try:
                return await self._execute_command(node, vmid, command, args)
            except asyncio.CancelledError:
                self.logger.warning(
                    f"Command call on VM {vmid} cancelled; a started process is left running"
                )
                raise

    async def _execute_command(
        self,
        node: str,
        vmid: str,
        command: str,
        args: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a command in a VM's console via QEMU guest agent.

        Implements a two-phase command execution process:
        1. Command Initiation:
           - Verifies VM exists and is running
           - Initiates command execution via guest agent
           - Captures command PID for tracking

        2. Result Collection:
           - Monitors command execution status
           - Captures command output and errors
           - Handles completion status

        Requirements:
        - VM must be running
        - QEMU guest agent must be installed and active
        - Command execution permissions must be enabled

        Args:
            node: Name of the node where VM is running (e.g., 'pve1')
            vmid: ID of the VM to execute command in (e.g., '100')
            command: Program (or, without ``args``, a command line split with shlex rules)
            args: Optional argument list; when given no splitting takes place. No shell is used.

        Returns:
            Dictionary containing command execution results:
            {
                "success": true only if the command exited with status 0,
                "output": "command output",
                "error": "error output if any",
                "exit_code": command_exit_code
            }

        Raises:
            ValueError: If:
                     - VM is not found
                     - VM is not running
                     - Guest agent is not available
            RuntimeError: If:
                       - Command execution fails
                       - Unable to get command status
                       - API communication errors occur
        """
        # The command may embed secrets and is never logged; it is scrubbed from error text
        # per call only (never stored in the global redaction registry).
        argv = self._build_argv(command, args)  # validation before any API call
        try:
            # Verify VM exists and is running
            # proxmoxer is synchronous; run every call in a worker thread so the
            # event loop (and /health) stays responsive.
            # The lazy connection resolves on attribute access, so the whole chain
            # (including the first connect) must be evaluated inside the worker thread.
            vm_status = await asyncio.to_thread(
                require_vm_status, self.proxmox, node, vmid, "execute_vm_command"
            )
            if vm_status["status"] != "running":
                self.logger.error(f"Failed to execute command on VM {vmid}: VM is not running")
                raise ValueError(f"VM {vmid} on node {node} is not running")

            self.logger.info(f"Executing command on VM {vmid} (node: {node})")

            # Use the guest agent exec endpoint
            endpoint = await asyncio.to_thread(lambda: self.proxmox.nodes(node).qemu(vmid).agent)

            # Execute the command using two-step process
            try:
                # Start command execution
                try:
                    exec_result = await asyncio.to_thread(
                        partial(endpoint("exec").post, command=argv)
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to start command on VM {vmid} (node: {node}): {type(e).__name__}"
                    )
                    self._raise_agent_hint(e, vmid)
                    self._raise_translated(e, node, vmid, command, argv)
                    raise RuntimeError(f"Failed to start command: {type(e).__name__}") from None

                if not isinstance(exec_result, dict) or "pid" not in exec_result:
                    raise RuntimeError("No PID returned from command execution")

                pid = exec_result["pid"]
                self.logger.info(f"Command started on VM {vmid} (PID: {pid})")

                # Poll exec-status with backoff until the command exits or the deadline passes.
                deadline = time.monotonic() + self.exec_timeout
                interval = self.POLL_START
                timed_out = False
                while True:
                    await asyncio.sleep(interval)
                    interval = min(interval * 2, self.POLL_MAX)
                    try:
                        console = await asyncio.to_thread(
                            partial(endpoint("exec-status").get, pid=pid)
                        )
                        if not console:
                            raise RuntimeError("No response from exec-status")
                    except Exception as e:
                        self.logger.error(
                            f"Failed to get command status for PID {pid}: {type(e).__name__}"
                        )
                        self._raise_agent_hint(e, vmid)
                        self._raise_translated(e, node, vmid, command, argv)
                        raise RuntimeError(
                            f"Failed to get command status: {type(e).__name__}"
                        ) from None
                    if not isinstance(console, dict) or console.get("exited"):
                        break
                    if time.monotonic() >= deadline:
                        timed_out = True
                        break
            except ValueError:
                raise
            except Exception as e:
                if getattr(e, "_pve_translated", False):
                    raise
                self.logger.error(f"API call failed on VM {vmid}: {type(e).__name__}")
                detail = redact_local(str(e), command, *argv)
                raise RuntimeError(f"API call failed: {detail}") from None

            truncated = False
            if isinstance(console, dict):
                output, cut_out = self._cap(console.get("out-data", ""))
                error, cut_err = self._cap(console.get("err-data", ""))
                truncated = (
                    cut_out
                    or cut_err
                    or bool(console.get("out-truncated") or console.get("err-truncated"))
                )
                exited = bool(console.get("exited", 0))
                exit_code = console.get("exitcode") if exited else None
                signal = console.get("signal") if exited else None
            else:
                # Some versions might return data differently
                output, truncated = self._cap(str(console))
                error = ""
                exit_code = 0
                exited = True
                signal = None

            if timed_out:
                self.logger.warning(f"Command on VM {vmid} still running at MCP wait limit")

            self.logger.info(
                f"Command finished on VM {vmid} (node: {node}, PID: {pid}, exit_code: {exit_code}, "
                f"exited: {exited}, timed_out: {timed_out}, "
                f"output_len: {len(output)}, error_len: {len(error)})"
            )

            # Success means the command exited normally with status 0. A command that is still
            # running (wait limit), was killed by a signal or exited non-zero is not a success.
            success = exited and not timed_out and not signal and exit_code == 0
            result = {
                "success": success,
                "output": output,
                "error": error,
                "exit_code": exit_code,
                "exited": exited,
                "signal": signal,
                "timed_out": timed_out,
                "truncated": truncated,
                "pid": pid,
            }
            if timed_out:
                result["message"] = "still running in the guest; MCP wait limit reached"
            return result

        except ValueError:
            # Re-raise ValueError for VM not running
            raise
        except Exception as e:
            if getattr(e, "_pve_translated", False):
                raise
            self.logger.error(f"Failed to execute command on VM {vmid}: {type(e).__name__}")
            detail = redact_local(str(e), command, *argv)
            raise RuntimeError(f"Failed to execute command: {detail}") from None
